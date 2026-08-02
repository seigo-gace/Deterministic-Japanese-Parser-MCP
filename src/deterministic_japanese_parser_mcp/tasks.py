from __future__ import annotations

from heapq import heappop, heappush

from .models import Intent, ItemStatus, Metaphor, Task


class TaskDecomposer:
    def __init__(self, doc: dict):
        self.by_intent = {
            item.get("intent"): item
            for item in doc.get("templates", [])
            if item.get("intent") != "workflow"
        }
        self.workflows = {
            item.get("name"): item
            for item in doc.get("templates", [])
            if item.get("intent") == "workflow"
        }
        self.last_cycles: list[dict] = []
        self.last_metrics: dict[str, int] = {
            "task_edge_count": 0,
            "task_cycle_count": 0,
        }

    @staticmethod
    def _overlaps(left: Intent, right: Intent) -> bool:
        return left.span.start < right.span.end and right.span.start < left.span.end

    @staticmethod
    def _overlaps_metaphor(intent: Intent, metaphor: Metaphor) -> bool:
        return (
            intent.span.start < metaphor.span.end
            and metaphor.span.start < intent.span.end
        )

    @staticmethod
    def _normalize_fragment(value: str | None) -> str:
        return (value or "").strip(" 、。！？\n\t")

    def _find_task_index(
        self,
        fragment: str | None,
        relation: Intent,
        tasks: list[Task],
        original_text: str,
    ) -> int | None:
        fragment = self._normalize_fragment(fragment)
        if not fragment:
            return None
        absolute_start = original_text.find(
            fragment, relation.span.start, relation.span.end
        )
        if absolute_start < 0:
            absolute_start = original_text.find(fragment)
        absolute_end = (
            absolute_start + len(fragment) if absolute_start >= 0 else -1
        )
        best: tuple[int, int, int] | None = None
        best_index: int | None = None
        for index, task in enumerate(tasks):
            target = self._normalize_fragment(task.target)
            source = self._normalize_fragment(task.original_span.source_text)
            score = 0
            if target == fragment:
                score += 100
            elif target and (fragment in target or target in fragment):
                score += 60
            if source and fragment in source:
                score += 40
            if (
                absolute_start >= 0
                and task.original_span.start < absolute_end
                and absolute_start < task.original_span.end
            ):
                score += 80
            if task.intent_type in {"sequence", "condition", "dependency"}:
                score -= 20
            if score <= 0:
                continue
            ranking = (
                score,
                -abs(task.original_span.start - max(0, absolute_start)),
                -index,
            )
            if best is None or ranking > best:
                best = ranking
                best_index = index
        return best_index

    def _build_edges(
        self,
        intents: list[Intent],
        tasks: list[Task],
        original_text: str,
    ) -> set[tuple[int, int]]:
        edges: set[tuple[int, int]] = set()
        for intent in intents:
            source_fragment: str | None = None
            target_fragment: str | None = None
            if intent.type == "sequence":
                source_fragment = intent.captures.get("first")
                target_fragment = intent.captures.get("second")
                if intent.captures.get("last"):
                    target_fragment = intent.captures["last"]
                    target_index = self._find_task_index(
                        target_fragment, intent, tasks, original_text
                    )
                    if target_index is not None:
                        for source_index, task in enumerate(tasks):
                            if (
                                source_index != target_index
                                and task.original_span.start
                                < tasks[target_index].original_span.start
                            ):
                                edges.add((source_index, target_index))
                    continue
            elif intent.type == "condition":
                source_fragment = intent.captures.get("condition")
                target_fragment = intent.captures.get("action")
            elif intent.type == "dependency":
                source_fragment = intent.captures.get("dependency")
                target_fragment = intent.captures.get("task")
            else:
                continue
            source_index = self._find_task_index(
                source_fragment, intent, tasks, original_text
            )
            target_index = self._find_task_index(
                target_fragment, intent, tasks, original_text
            )
            if (
                source_index is not None
                and target_index is not None
                and source_index != target_index
            ):
                edges.add((source_index, target_index))
        return edges

    @staticmethod
    def _topological_order(
        tasks: list[Task],
        edges: set[tuple[int, int]],
    ) -> list[int] | None:
        outgoing: dict[int, set[int]] = {
            index: set() for index in range(len(tasks))
        }
        indegree = {index: 0 for index in range(len(tasks))}
        for source, target in edges:
            if target not in outgoing[source]:
                outgoing[source].add(target)
                indegree[target] += 1
        queue: list[tuple[int, int]] = []
        for index, degree in indegree.items():
            if degree == 0:
                heappush(queue, (tasks[index].original_span.start, index))
        order: list[int] = []
        while queue:
            _, index = heappop(queue)
            order.append(index)
            for target in sorted(
                outgoing[index],
                key=lambda item: (tasks[item].original_span.start, item),
            ):
                indegree[target] -= 1
                if indegree[target] == 0:
                    heappush(
                        queue,
                        (tasks[target].original_span.start, target),
                    )
        return order if len(order) == len(tasks) else None

    def build(
        self,
        intents: list[Intent],
        metaphors: list[Metaphor] | None = None,
        original_text: str = "",
    ) -> list[Task]:
        self.last_cycles = []
        metaphors = metaphors or []
        executable = {
            "request",
            "prohibition",
            "preserve",
            "modify",
            "remove",
            "comparison",
            "action",
            "decision",
            "correction",
            "condition",
            "exception",
            "priority",
            "scope",
            "out_of_scope",
            "dependency",
            "completion_criteria",
            "verification_criteria",
            "premise",
        }
        specific = executable - {"request"}
        selected: list[Intent] = []
        for intent in intents:
            if intent.type not in executable:
                continue
            if intent.type == "request" and (
                any(
                    other.type in specific and self._overlaps(intent, other)
                    for other in intents
                )
                or any(
                    self._overlaps_metaphor(intent, metaphor)
                    for metaphor in metaphors
                )
            ):
                continue
            selected.append(intent)

        candidates: list[tuple[int, int, Task]] = []
        for intent in selected:
            template = self.by_intent.get(intent.type, {})
            target = (
                intent.captures.get("target")
                or intent.captures.get("action")
                or intent.value
            )
            candidates.append((
                intent.span.start,
                1,
                Task(
                    task_id="",
                    action=template.get("action", intent.type),
                    target=target,
                    intent_type=intent.type,
                    execution_order=0,
                    verification_criteria=template.get("verification", []),
                    external_action=intent.type in {"modify", "remove", "action"},
                    status=ItemStatus.RESOLVED,
                    original_span=intent.span,
                ),
            ))

        for metaphor in metaphors:
            candidates.append((
                metaphor.span.start,
                0,
                Task(
                    task_id="",
                    action=metaphor.interpretation,
                    target=metaphor.expression,
                    intent_type="metaphor",
                    execution_order=0,
                    verification_criteria=[
                        "原文spanが存在する",
                        "辞書Versionが応答に含まれる",
                    ],
                    external_action=False,
                    status=metaphor.status,
                    original_span=metaphor.span,
                ),
            ))

        ordered_candidates = sorted(
            candidates,
            key=lambda item: (item[0], item[1], item[2].target or ""),
        )
        tasks = [item[2] for item in ordered_candidates]
        edges = (
            self._build_edges(intents, tasks, original_text)
            if original_text
            else set()
        )
        order = self._topological_order(tasks, edges)
        if order is None:
            self.last_cycles.append({
                "type": "task_dependency_cycle",
                "edges": sorted([list(edge) for edge in edges]),
            })
            order = list(range(len(tasks)))

        task_id_by_old = {
            old_index: f"T-{new_index:03d}"
            for new_index, old_index in enumerate(order, 1)
        }
        dependencies_by_old: dict[int, list[str]] = {
            index: [] for index in range(len(tasks))
        }
        for source, target in sorted(edges):
            dependencies_by_old[target].append(task_id_by_old[source])

        output: list[Task] = []
        for execution_order, old_index in enumerate(order, 1):
            task = tasks[old_index]
            output.append(task.model_copy(update={
                "task_id": task_id_by_old[old_index],
                "execution_order": execution_order,
                "dependencies": sorted(
                    set(dependencies_by_old[old_index])
                ),
            }))
        self.last_metrics = {
            "task_edge_count": len(edges),
            "task_cycle_count": len(self.last_cycles),
        }
        return output
