from .models import Intent


def _key(intent: Intent) -> str:
    return (intent.captures.get("target") or intent.captures.get("action") or intent.value).replace(" ", "")


def _related(left: str, right: str) -> bool:
    return bool(left and right and (left in right or right in left))


def detect(intents: list[Intent], protected_elements: list[str] | None = None) -> list[dict]:
    result: list[dict] = []
    prohibits = [item for item in intents if item.type == "prohibition"]
    actions = [item for item in intents if item.type in {"action", "request", "modify", "remove"}]
    preserves = [item for item in intents if item.type == "preserve"]
    changes = [item for item in intents if item.type in {"modify", "remove", "action"}]

    for left in prohibits:
        for right in actions:
            if _related(_key(left), _key(right)):
                result.append({
                    "type": "prohibition_conflict",
                    "left": left.model_dump(),
                    "right": right.model_dump(),
                })

    for left in preserves:
        for right in changes:
            if _related(_key(left), _key(right)):
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
            if _related(normalized, _key(change)):
                result.append({
                    "type": "protected_element_conflict",
                    "protected_element": protected,
                    "right": change.model_dump(),
                })

    # Stable, content-based de-duplication.
    unique: dict[tuple, dict] = {}
    for item in result:
        right = item.get("right", {})
        key = (
            item.get("type"),
            item.get("protected_element"),
            right.get("rule_id"),
            right.get("span", {}).get("start"),
        )
        unique.setdefault(key, item)
    return list(unique.values())
