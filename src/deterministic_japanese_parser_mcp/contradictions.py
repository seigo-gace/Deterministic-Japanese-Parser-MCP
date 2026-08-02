from __future__ import annotations

from .canonical import Canonicalizer
from .models import Intent


def _key(intent: Intent) -> str:
    return (
        intent.captures.get("target")
        or intent.captures.get("action")
        or intent.captures.get("task")
        or intent.value
    ).replace(" ", "")


def _related(
    left: str,
    right: str,
    canonicalizer: Canonicalizer | None = None,
) -> bool:
    if canonicalizer is not None:
        return canonicalizer.related(left, right)
    return bool(left and right and (left in right or right in left))


def detect(
    intents: list[Intent],
    protected_elements: list[str] | None = None,
    canonicalizer: Canonicalizer | None = None,
) -> list[dict]:
    result: list[dict] = []
    prohibits = [item for item in intents if item.type == "prohibition"]
    actions = [
        item
        for item in intents
        if item.type in {"action", "request", "modify", "remove"}
    ]
    preserves = [item for item in intents if item.type == "preserve"]
    changes = [
        item for item in intents if item.type in {"modify", "remove", "action"}
    ]
    key_cache = {id(item): _key(item) for item in intents}

    for left in prohibits:
        for right in actions:
            if _related(
                key_cache[id(left)], key_cache[id(right)], canonicalizer
            ):
                result.append({
                    "type": "prohibition_conflict",
                    "left": left.model_dump(),
                    "right": right.model_dump(),
                })

    for left in preserves:
        for right in changes:
            if _related(
                key_cache[id(left)], key_cache[id(right)], canonicalizer
            ):
                result.append({
                    "type": "preserve_change_conflict",
                    "left": left.model_dump(),
                    "right": right.model_dump(),
                })

    for protected in protected_elements or []:
        normalized = protected.replace(" ", "")
        if not normalized:
            continue
        for change in changes:
            if _related(
                normalized, key_cache[id(change)], canonicalizer
            ):
                result.append({
                    "type": "protected_element_conflict",
                    "protected_element": protected,
                    "right": change.model_dump(),
                })

    unique: dict[tuple, dict] = {}
    for item in result:
        right = item.get("right", {})
        left = item.get("left", {})
        key = (
            item.get("type"),
            item.get("protected_element"),
            left.get("rule_id"),
            left.get("span", {}).get("start"),
            right.get("rule_id"),
            right.get("span", {}).get("start"),
        )
        unique.setdefault(key, item)
    return list(unique.values())
