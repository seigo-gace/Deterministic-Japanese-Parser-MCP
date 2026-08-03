from __future__ import annotations

import regex

from .literal_index import LiteralIndex
from .models import ItemStatus, Metaphor
from .normalizer import span_to_original

_SENTENCE_BOUNDARY = regex.compile(r"[。！？\n]")


class MetaphorMatcher:
    def __init__(self, doc: dict, timeout_ms: int = 25):
        self.entries = doc.get("entries", [])
        self.timeout = max(0.001, timeout_ms / 1000)
        literal_index: dict[str, list[dict]] = {}
        self.compiled_patterns: list[tuple[dict, regex.Pattern]] = []
        for item in self.entries:
            for literal in [item["expression"], *item.get("aliases", [])]:
                if literal:
                    literal_index.setdefault(literal, []).append(item)
            for pattern in item.get("patterns", []):
                self.compiled_patterns.append((item, regex.compile(pattern)))
        self.literal_index = literal_index
        self.literal_matcher = LiteralIndex(literal_index)
        self.last_timeouts: list[dict] = []
        self.last_metrics: dict[str, int] = {
            "literal_count": len(literal_index),
            "literal_state_count": self.literal_matcher.state_count,
            "regex_pattern_count": len(self.compiled_patterns),
            "literal_candidate_count": 0,
        }

    @staticmethod
    def _clause_window(text: str, start: int, end: int) -> str:
        left = 0
        for match in _SENTENCE_BOUNDARY.finditer(text, 0, start):
            left = match.end()
        right_match = _SENTENCE_BOUNDARY.search(text, end)
        right = right_match.start() if right_match else len(text)
        return text[left:right]

    @staticmethod
    def _status(item: dict, context_matches: list[str]) -> ItemStatus:
        policy = item.get("context_policy", "optional")
        if policy == "required_any" and not context_matches:
            return ItemStatus.AMBIGUOUS
        if policy == "forbidden_any" and context_matches:
            return ItemStatus.UNSUPPORTED
        return ItemStatus.RESOLVED

    def _literal_matches(self, text: str) -> list[tuple[dict, int, int]]:
        output: list[tuple[dict, int, int]] = []
        seen: set[tuple[str, int, int]] = set()
        for literal, start, end in self.literal_matcher.find(text):
            for item in self.literal_index[literal]:
                key = (item["expression"], start, end)
                if key not in seen:
                    seen.add(key)
                    output.append((item, start, end))
        return output

    def find(self, text, mapping, original) -> list[Metaphor]:
        self.last_timeouts = []
        raw_matches = self._literal_matches(text)
        literal_candidate_count = len(raw_matches)
        for item, pattern in self.compiled_patterns:
            try:
                for match in pattern.finditer(text, timeout=self.timeout):
                    raw_matches.append((item, match.start(), match.end()))
            except TimeoutError:
                self.last_timeouts.append({
                    "phase": "metaphor_detection",
                    "expression": item.get("expression"),
                    "status": "TIMEOUT",
                })

        output: list[Metaphor] = []
        for item, start, end in raw_matches:
            window = self._clause_window(text, start, end)
            context_matches = [
                value for value in item.get("context", []) if value in window
            ]
            output.append(Metaphor(
                expression=item["expression"],
                interpretation=item["interpretation"],
                domain=item.get("domain", "general"),
                context_matches=context_matches,
                span=span_to_original(start, end, mapping, original),
                status=self._status(item, context_matches),
            ))

        unique: dict[tuple, Metaphor] = {}
        for entry in sorted(
            output,
            key=lambda value: (
                value.span.start,
                -len(value.span.source_text),
                value.expression,
            ),
        ):
            unique.setdefault((entry.span.start, entry.expression), entry)
        self.last_metrics = {
            "literal_count": len(self.literal_index),
            "literal_state_count": self.literal_matcher.state_count,
            "regex_pattern_count": len(self.compiled_patterns),
            "literal_candidate_count": literal_candidate_count,
        }
        return list(unique.values())
