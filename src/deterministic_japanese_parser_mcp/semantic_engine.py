from __future__ import annotations

from time import perf_counter

from .engine import ParserEngine as CoreParserEngine
from .models import AnalyzeRequest, ExecutionMode, OverallStatus
from .semantic_data_runtime import SemanticDataRuntime


class ParserEngine(CoreParserEngine):
    """Core parser with approved unified semantic data pack integration."""

    def __init__(self, settings=None):
        if settings is None:
            super().__init__()
        else:
            super().__init__(settings)
        self.semantic_data = SemanticDataRuntime(
            self.settings.system_dict_dir / "compiled" / "semantic_data"
        )

    def analyze(self, request: AnalyzeRequest, *, exhaustive_rules: bool = False):
        response = super().analyze(request, exhaustive_rules=exhaustive_rules)
        started = perf_counter()
        graph = self.semantic_data.enrich(
            response.meaning_graph,
            tokens=response.tokens,
            original_text=request.original_text,
            conversation_context=request.conversation_context,
            known_entities=request.known_entities,
        )
        semantic_ms = round((perf_counter() - started) * 1000, 3)
        task_graph = self.action_tasks.build(graph)
        execution_allowed, blocked, action_closure = self.guard.evaluate(
            graph,
            contradictions=response.contradictions,
            unsupported=response.unsupported_elements,
            timeouts=response.timeouts,
            external_action=request.execution_mode == ExecutionMode.EXTERNAL_ACTION,
        )
        overall = response.overall_status
        if graph.unresolved and overall == OverallStatus.COMPLETE:
            overall = OverallStatus.PARTIAL
        previous_total = float(response.metrics.get("total_ms", 0.0))
        total_ms = round(previous_total + semantic_ms, 3)
        hard_deadline_met = total_ms <= self.settings.hard_deadline_ms
        if not hard_deadline_met:
            overall = OverallStatus.PARTIAL
            if request.execution_mode == ExecutionMode.EXTERNAL_ACTION:
                execution_allowed = False
                blocked = list(dict.fromkeys([*blocked, "TIMEOUT"]))
        metrics = {
            **response.metrics,
            **self.semantic_data.last_metrics,
            **self.action_tasks.last_metrics,
            "semantic_data_enrichment_ms": semantic_ms,
            "action_task_count": len(task_graph.tasks),
            "action_relevance_node_count": len(action_closure),
            "semantic_hash": graph.semantic_hash,
            "total_ms": total_ms,
            "elapsed_ms": total_ms,
            "hard_deadline_met": hard_deadline_met,
        }
        return response.model_copy(update={
            "overall_status": overall,
            "meaning_graph": graph,
            "task_graph": task_graph,
            "execution_allowed": (
                execution_allowed
                if request.execution_mode == ExecutionMode.EXTERNAL_ACTION
                else True
            ),
            "blocked_reasons": (
                blocked
                if request.execution_mode == ExecutionMode.EXTERNAL_ACTION
                else []
            ),
            "metrics": metrics,
        })
