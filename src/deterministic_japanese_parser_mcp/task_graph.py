from __future__ import annotations

from heapq import heappop, heappush

from .grammar_kernel import ACTION_INTENTS
from .models import ItemStatus, MeaningGraph, Task, TaskConstraint, TaskGraph


_RELATION_CONSTRAINTS = {
    "prohibits": "prohibition",
    "preserves": "preserve",
    "conditions": "condition",
    "excepts": "exception",
    "prioritizes": "priority",
    "limits": "scope",
    "excludes": "out_of_scope",
    "completion_gate": "completion_criteria",
    "verification_gate": "verification_criteria",
    "premise_for": "premise",
}


class ActionTaskGraphBuilder:
    """Build executable actions separately from semantic constraints."""

    def __init__(self, template_doc: dict) -> None:
        self.by_intent = {
            item.get("intent"): item
            for item in template_doc.get("templates", [])
            if item.get("intent") != "workflow"
        }
        self.last_cycles: list[dict] = []
        self.last_metrics = {
            "action_task_count": 0,
            "task_constraint_count": 0,
            "action_task_edge_count": 0,
            "suppressed_generic_request_count": 0,
        }

    @staticmethod
    def _target(proposition) -> str:
        for role in ("object", "task", "action", "result", "scope"):
            for argument in proposition.arguments:
                if argument.role == role and argument.value:
                    return argument.value
        return proposition.value

    @staticmethod
    def _overlaps(left, right) -> bool:
        return (
            left.source_span.start < right.source_span.end
            and right.source_span.start < left.source_span.end
        )

    @staticmethod
    def _order(
        count: int,
        edges: set[tuple[int, int]],
        spans: list[int],
    ) -> list[int] | None:
        outgoing = {index: set() for index in range(count)}
        indegree = {index: 0 for index in range(count)}
        for source, target in edges:
            if target not in outgoing[source]:
                outgoing[source].add(target)
                indegree[target] += 1
        queue: list[tuple[int, int]] = []
        for index, degree in indegree.items():
            if degree == 0:
                heappush(queue, (spans[index], index))
        output: list[int] = []
        while queue:
            _, index = heappop(queue)
            output.append(index)
            for target in sorted(
                outgoing[index],
                key=lambda item: (spans[item], item),
            ):
                indegree[target] -= 1
                if indegree[target] == 0:
                    heappush(queue, (spans[target], target))
        return output if len(output) == count else None

    def build(self, graph: MeaningGraph) -> TaskGraph:
        self.last_cycles = []
        proposition_by_id = {
            item.proposition_id: item for item in graph.propositions
        }
        candidates = [
            item
            for item in graph.propositions
            if item.intent_type in ACTION_INTENTS and item.executable_candidate
        ]
        specific = [
            item for item in candidates if item.intent_type != "request"
        ]
        selected = [
            item
            for item in candidates
            if item.intent_type != "request"
            or not any(self._overlaps(item, other) for other in specific)
        ]
        selected.sort(
            key=lambda item: (item.source_span.start, item.proposition_id)
        )
        selected_by_id = {
            item.proposition_id: item for item in selected
        }
        index_by_prop = {
            item.proposition_id: index for index, item in enumerate(selected)
        }
        constraints_by_target: dict[str, list[TaskConstraint]] = {
            item.proposition_id: [] for item in selected
        }
        all_constraints: list[TaskConstraint] = []
        dependency_edges: set[tuple[int, int]] = set()
        relation_by_edge: dict[tuple[int, int], str] = {}

        def resolve_selected_target(target_id: str) -> str | None:
            if target_id in selected_by_id:
                return target_id
            target = proposition_by_id.get(target_id)
            if target is None or target.intent_type != "request":
                return None
            overlapping = [
                item for item in selected if self._overlaps(target, item)
            ]
            if not overlapping:
                return None
            overlapping.sort(key=lambda item: (
                0 if item.clause_id == target.clause_id else 1,
                abs(item.source_span.start - target.source_span.start),
                item.source_span.start,
                item.proposition_id,
            ))
            return overlapping[0].proposition_id

        for edge in graph.scope_edges:
            resolved_source_id = resolve_selected_target(edge.source_id)
            resolved_target_id = resolve_selected_target(edge.target_id)
            if edge.relation in {"precedes", "depends_on"}:
                if (
                    resolved_source_id in index_by_prop
                    and resolved_target_id in index_by_prop
                ):
                    source = index_by_prop[resolved_source_id]
                    target = index_by_prop[resolved_target_id]
                    pair = (
                        (source, target)
                        if edge.relation == "precedes"
                        else (target, source)
                    )
                    if pair[0] != pair[1]:
                        dependency_edges.add(pair)
                        relation_by_edge[pair] = edge.relation
                continue
            constraint_type = _RELATION_CONSTRAINTS.get(edge.relation)
            if not constraint_type or resolved_target_id not in constraints_by_target:
                continue
            source = proposition_by_id.get(edge.source_id)
            constraint = TaskConstraint(
                constraint_type=constraint_type,
                value=self._target(source) if source else edge.relation,
                source_proposition_id=edge.source_id,
                source_span=source.source_span if source else None,
                status=edge.status,
            )
            constraints_by_target[resolved_target_id].append(constraint)
            all_constraints.append(constraint)

        provisional: list[Task] = []
        for proposition in selected:
            template = self.by_intent.get(proposition.intent_type, {})
            structured = constraints_by_target[proposition.proposition_id]
            provisional.append(Task(
                task_id="",
                action=template.get("action", proposition.predicate),
                target=self._target(proposition),
                intent_type=proposition.intent_type,
                constraints=[
                    f"{item.constraint_type}:{item.value}"
                    for item in structured
                ],
                structured_constraints=structured,
                completion_criteria=[
                    item.value
                    for item in structured
                    if item.constraint_type == "completion_criteria"
                ],
                verification_criteria=[
                    *template.get("verification", []),
                    *[
                        item.value
                        for item in structured
                        if item.constraint_type == "verification_criteria"
                    ],
                ],
                external_action=(
                    proposition.intent_type in {"modify", "remove", "action"}
                ),
                status=proposition.status,
                original_span=proposition.source_span,
                proposition_id=proposition.proposition_id,
            ))

        order = self._order(
            len(provisional),
            dependency_edges,
            [item.original_span.start for item in provisional],
        )
        if order is None:
            order = list(range(len(provisional)))
            self.last_cycles.append({
                "type": "action_task_dependency_cycle",
                "edges": sorted([list(item) for item in dependency_edges]),
            })
        task_id_by_old = {
            old_index: f"A-{new_index:03d}"
            for new_index, old_index in enumerate(order, 1)
        }
        dependencies = {
            index: [] for index in range(len(provisional))
        }
        for source, target in dependency_edges:
            dependencies[target].append(task_id_by_old[source])
        tasks = [
            provisional[old_index].model_copy(update={
                "task_id": task_id_by_old[old_index],
                "execution_order": execution_order,
                "dependencies": sorted(set(dependencies[old_index])),
            })
            for execution_order, old_index in enumerate(order, 1)
        ]
        status = (
            ItemStatus.RESOLVED
            if all(item.status == ItemStatus.RESOLVED for item in tasks)
            else ItemStatus.AMBIGUOUS
        )
        self.last_metrics = {
            "action_task_count": len(tasks),
            "task_constraint_count": len(all_constraints),
            "action_task_edge_count": len(dependency_edges),
            "suppressed_generic_request_count": len(candidates) - len(selected),
        }
        return TaskGraph(
            tasks=tasks,
            edges=[
                {
                    "source": task_id_by_old[source],
                    "target": task_id_by_old[target],
                    "relation": relation_by_edge[(source, target)],
                }
                for source, target in sorted(dependency_edges)
            ],
            constraints=all_constraints,
            status=status,
        )
