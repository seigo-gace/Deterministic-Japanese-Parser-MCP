from __future__ import annotations

from time import perf_counter
import warnings

import regex

from .models import Intent, ItemStatus
from .normalizer import span_to_original

try:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        import sre_parse  # type: ignore[deprecated]
except ImportError:  # pragma: no cover
    sre_parse = None


def _literal_run(tokens, start: int) -> tuple[str, int]:
    chars: list[str] = []
    index = start
    while index < len(tokens) and tokens[index][0] is sre_parse.LITERAL:
        chars.append(chr(tokens[index][1]))
        index += 1
    return "".join(chars), index


def _proven_triggers(tokens) -> set[str] | None:
    """Return literals whose union is guaranteed to cover every regex match.

    Unsupported or optional constructs return no proof, leaving the rule on the
    exhaustive fallback path. No rule is skipped unless the trigger requirement
    is mechanically proven from its regex structure.
    """
    if sre_parse is None:
        return None
    guaranteed_parts: list[set[str]] = []
    index = 0
    while index < len(tokens):
        op, argument = tokens[index]
        if op is sre_parse.LITERAL:
            literal, index = _literal_run(tokens, index)
            if literal:
                guaranteed_parts.append({literal})
            continue
        candidate: set[str] | None = None
        if op is sre_parse.SUBPATTERN:
            candidate = _proven_triggers(argument[-1])
        elif op is sre_parse.BRANCH:
            branch_sets: list[set[str]] = []
            for branch in argument[1]:
                branch_triggers = _proven_triggers(branch)
                if not branch_triggers:
                    branch_sets = []
                    break
                branch_sets.append(branch_triggers)
            if branch_sets:
                candidate = set().union(*branch_sets)
        elif op in {sre_parse.MAX_REPEAT, sre_parse.MIN_REPEAT}:
            minimum, _, repeated = argument
            if minimum >= 1:
                candidate = _proven_triggers(repeated)
        elif op is sre_parse.IN:
            literals: set[str] = set()
            valid = True
            for inner_op, inner_argument in argument:
                if inner_op is sre_parse.LITERAL:
                    literals.add(chr(inner_argument))
                else:
                    valid = False
                    break
            if valid and literals:
                candidate = literals
        if candidate:
            guaranteed_parts.append(candidate)
        index += 1
    if not guaranteed_parts:
        return None
    return set().union(*guaranteed_parts)


def _extract_proven_triggers(pattern: str) -> tuple[str, ...]:
    if sre_parse is None:
        return ()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            parsed = sre_parse.parse(pattern)
        triggers = _proven_triggers(parsed)
    except Exception:
        return ()
    if not triggers:
        return ()
    return tuple(sorted(triggers, key=lambda item: (-len(item), item)))


class RuleEngine:
    def __init__(self, doc: dict, timeout_ms: int | None = None):
        configured = timeout_ms if timeout_ms is not None else doc.get("timeout_ms", 25)
        self.timeout = max(0.001, configured / 1000)
        self.compiled: list[tuple[str, dict, regex.Pattern]] = []
        self.always_scan: set[int] = set()
        trigger_index: dict[str, set[int]] = {}
        for intent, items in doc.get("intents", {}).items():
            for item in items:
                if not item.get("enabled", True):
                    continue
                compiled = regex.compile(item["pattern"])
                rule_index = len(self.compiled)
                self.compiled.append((intent, item, compiled))
                triggers = _extract_proven_triggers(item["pattern"])
                if not triggers or compiled.flags & regex.IGNORECASE:
                    self.always_scan.add(rule_index)
                    continue
                for literal in triggers:
                    trigger_index.setdefault(literal, set()).add(rule_index)
        self.trigger_index = {
            literal: frozenset(indices)
            for literal, indices in trigger_index.items()
        }
        by_first: dict[str, list[str]] = {}
        for literal in self.trigger_index:
            by_first.setdefault(literal[0], []).append(literal)
        self.triggers_by_first = {
            char: tuple(sorted(values, key=lambda item: (-len(item), item)))
            for char, values in by_first.items()
        }
        self.last_metrics = {
            "total_rule_count": len(self.compiled),
            "candidate_rule_count": len(self.compiled),
            "indexed_rule_count": len(self.compiled) - len(self.always_scan),
            "always_scan_rule_count": len(self.always_scan),
        }

    def candidate_indices(self, text: str) -> set[int]:
        candidates = set(self.always_scan)
        matched_literals: set[str] = set()
        for index, char in enumerate(text):
            for literal in self.triggers_by_first.get(char, ()):
                if literal in matched_literals:
                    continue
                if text.startswith(literal, index):
                    matched_literals.add(literal)
                    candidates.update(self.trigger_index[literal])
        return candidates

    def _extract_indices(
        self,
        indices: set[int],
        text: str,
        mapping,
        original: str,
        deadline_at: float | None,
    ) -> tuple[list[Intent], list[dict]]:
        found: list[Intent] = []
        timeouts: list[dict] = []
        for rule_index, (intent, item, pattern) in enumerate(self.compiled):
            if rule_index not in indices:
                continue
            remaining = self.timeout
            if deadline_at is not None:
                remaining = min(remaining, deadline_at - perf_counter())
                if remaining <= 0:
                    timeouts.append({
                        "phase": "intent_extraction",
                        "rule_id": item["id"],
                        "status": "TIMEOUT",
                    })
                    break
            try:
                for match in pattern.finditer(text, timeout=max(0.001, remaining)):
                    captures = {
                        key: value
                        for key, value in match.groupdict().items()
                        if value is not None
                    }
                    value = next(iter(captures.values()), match.group(0))
                    found.append(Intent(
                        type=intent,
                        value=value.strip(),
                        captures={key: value.strip() for key, value in captures.items()},
                        rule_id=item["id"],
                        priority=item.get("priority", 0),
                        span=span_to_original(
                            match.start(), match.end(), mapping, original
                        ),
                        status=ItemStatus.RESOLVED,
                    ))
            except TimeoutError:
                timeouts.append({
                    "phase": "intent_extraction",
                    "rule_id": item["id"],
                    "status": "TIMEOUT",
                })

        unique: dict[tuple, Intent] = {}
        for result in sorted(
            found,
            key=lambda value: (value.span.start, -value.priority, value.rule_id or ""),
        ):
            key = (result.type, result.span.start, result.span.end, result.value)
            unique.setdefault(key, result)
        results = list(unique.values())

        reference_results = sorted(
            (item for item in results if item.type == "reference"),
            key=lambda item: (
                item.span.start,
                -(item.span.end - item.span.start),
                -item.priority,
                item.rule_id or "",
            ),
        )
        kept_reference_ids: set[int] = set()
        kept_references: list[Intent] = []
        for item in reference_results:
            if any(
                existing.span.start <= item.span.start
                and existing.span.end >= item.span.end
                for existing in kept_references
            ):
                continue
            kept_references.append(item)
            kept_reference_ids.add(id(item))
        results = [
            item
            for item in results
            if item.type != "reference" or id(item) in kept_reference_ids
        ]
        return results, timeouts

    def extract(
        self,
        text,
        mapping,
        original,
        deadline_at: float | None = None,
    ) -> tuple[list[Intent], list[dict]]:
        candidates = self.candidate_indices(text)
        self.last_metrics = {
            "total_rule_count": len(self.compiled),
            "candidate_rule_count": len(candidates),
            "indexed_rule_count": len(self.compiled) - len(self.always_scan),
            "always_scan_rule_count": len(self.always_scan),
        }
        return self._extract_indices(
            candidates, text, mapping, original, deadline_at
        )

    def extract_exhaustive(
        self,
        text,
        mapping,
        original,
        deadline_at: float | None = None,
    ) -> tuple[list[Intent], list[dict]]:
        all_indices = set(range(len(self.compiled)))
        return self._extract_indices(
            all_indices, text, mapping, original, deadline_at
        )
