from .models import Intent, ItemStatus, Metaphor, Task


class TaskDecomposer:
    def __init__(self, doc: dict):
        self.by_intent = {
            item.get("intent"): item
            for item in doc.get("templates", [])
            if item.get("intent") != "workflow"
        }

    @staticmethod
    def _overlaps(left: Intent, right: Intent) -> bool:
        return left.span.start < right.span.end and right.span.start < left.span.end

    @staticmethod
    def _overlaps_metaphor(intent: Intent, metaphor: Metaphor) -> bool:
        return intent.span.start < metaphor.span.end and metaphor.span.start < intent.span.end

    def build(self, intents: list[Intent], metaphors: list[Metaphor] | None = None) -> list[Task]:
        metaphors = metaphors or []
        executable = {
            "request", "prohibition", "preserve", "modify", "remove", "comparison",
            "action", "decision", "correction", "condition", "exception", "priority",
            "scope", "out_of_scope", "dependency", "completion_criteria",
            "verification_criteria", "premise",
        }
        specific = executable - {"request"}
        selected: list[Intent] = []
        for intent in intents:
            if intent.type not in executable:
                continue
            # Broad request rules maximize recall. They must not produce a duplicate Task when a
            # more specific intent or a resolved operational expression covers the same text.
            if intent.type == "request" and (
                any(other.type in specific and self._overlaps(intent, other) for other in intents)
                or any(self._overlaps_metaphor(intent, metaphor) for metaphor in metaphors)
            ):
                continue
            selected.append(intent)

        candidates: list[tuple[int, int, Task]] = []
        for intent in selected:
            template = self.by_intent.get(intent.type, {})
            target = intent.captures.get("target") or intent.captures.get("action") or intent.value
            candidates.append(
                (
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
                )
            )

        for metaphor in metaphors:
            candidates.append(
                (
                    metaphor.span.start,
                    0,
                    Task(
                        task_id="",
                        action=metaphor.interpretation,
                        target=metaphor.expression,
                        intent_type="metaphor",
                        execution_order=0,
                        verification_criteria=["原文spanが存在する", "辞書Versionが応答に含まれる"],
                        external_action=False,
                        status=metaphor.status,
                        original_span=metaphor.span,
                    ),
                )
            )

        ordered = sorted(candidates, key=lambda item: (item[0], item[1], item[2].target or ""))
        tasks: list[Task] = []
        for index, (_, _, task) in enumerate(ordered, 1):
            tasks.append(task.model_copy(update={"task_id": f"T-{index:03d}", "execution_order": index}))
        return tasks
