from __future__ import annotations

from .canonical import Canonicalizer
from .models import MeaningGraph


def _target(proposition) -> str:
    for role in ("object", "task", "action", "result", "scope"):
        for argument in proposition.arguments:
            if argument.role == role and argument.value:
                return argument.value
    return proposition.value


def detect_graph(
    graph: MeaningGraph,
    protected_elements: list[str] | None = None,
    canonicalizer: Canonicalizer | None = None,
) -> list[dict]:
    def related(left: str, right: str) -> bool:
        if canonicalizer is not None:
            return canonicalizer.related(left, right)
        return bool(left and right and (left in right or right in left))

    actions = [
        item
        for item in graph.propositions
        if item.intent_type in {"modify", "remove", "action"}
        and item.executable_candidate
    ]
    constraints = [
        item
        for item in graph.propositions
        if item.intent_type in {"preserve", "prohibition"}
    ]
    output: list[dict] = []
    for constraint in constraints:
        for action in actions:
            if related(_target(constraint), _target(action)):
                output.append({
                    "type": (
                        "preserve_change_conflict"
                        if constraint.intent_type == "preserve"
                        else "prohibition_conflict"
                    ),
                    "left_proposition_id": constraint.proposition_id,
                    "right_proposition_id": action.proposition_id,
                    "left": constraint.model_dump(mode="json"),
                    "right": action.model_dump(mode="json"),
                })
    for protected in protected_elements or []:
        for action in actions:
            if related(protected, _target(action)):
                output.append({
                    "type": "protected_element_conflict",
                    "protected_element": protected,
                    "right_proposition_id": action.proposition_id,
                    "right": action.model_dump(mode="json"),
                })
    unique: dict[tuple, dict] = {}
    for item in output:
        key = (
            item.get("type"),
            item.get("protected_element"),
            item.get("left_proposition_id"),
            item.get("right_proposition_id"),
        )
        unique.setdefault(key, item)
    return list(unique.values())
