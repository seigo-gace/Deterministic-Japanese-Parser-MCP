from time import perf_counter

import regex

from .models import Intent, ItemStatus
from .normalizer import span_to_original


class RuleEngine:
    def __init__(self, doc: dict):
        self.timeout = max(0.001, doc.get("timeout_ms", 25) / 1000)
        self.compiled = []
        for intent, items in doc.get("intents", {}).items():
            for item in items:
                if not item.get("enabled", True):
                    continue
                self.compiled.append((intent, item, regex.compile(item["pattern"])))

    def extract(self, text, mapping, original, deadline_at: float | None = None) -> tuple[list[Intent], list[dict]]:
        found: list[Intent] = []
        timeouts: list[dict] = []
        for intent, item, pattern in self.compiled:
            remaining = self.timeout
            if deadline_at is not None:
                remaining = min(remaining, deadline_at - perf_counter())
                if remaining <= 0:
                    timeouts.append({"phase": "intent_extraction", "rule_id": item["id"], "status": "TIMEOUT"})
                    break
            try:
                for match in pattern.finditer(text, timeout=max(0.001, remaining)):
                    captures = {key: value for key, value in match.groupdict().items() if value is not None}
                    value = next(iter(captures.values()), match.group(0))
                    found.append(
                        Intent(
                            type=intent,
                            value=value.strip(),
                            captures={key: value.strip() for key, value in captures.items()},
                            rule_id=item["id"],
                            priority=item.get("priority", 0),
                            span=span_to_original(match.start(), match.end(), mapping, original),
                            status=ItemStatus.RESOLVED,
                        )
                    )
            except TimeoutError:
                timeouts.append({"phase": "intent_extraction", "rule_id": item["id"], "status": "TIMEOUT"})

        unique: dict[tuple, Intent] = {}
        for result in sorted(found, key=lambda value: (value.span.start, -value.priority, value.rule_id or "")):
            key = (result.type, result.span.start, result.span.end, result.value)
            unique.setdefault(key, result)
        return list(unique.values()), timeouts
