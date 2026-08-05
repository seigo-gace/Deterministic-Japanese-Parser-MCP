from __future__ import annotations

from time import perf_counter

from .engine import ParserEngine as CoreParserEngine
from .models import AnalyzeRequest, ExecutionMode, OverallStatus
from .semantic_candidate_runtime import SemanticCandidateRuntime
from .semantic_data_runtime import SemanticDataRuntime


class ParserEngine(CoreParserEngine):
    """Core parser with candidate-only and approved semantic pack integration."""

    def __init__(self, settings=None):
        if settings is None:
            super().__init__()
        else:
            super().__init__(settings)
        compiled_root = self.settings.system_dict_dir / "compiled"
        self.semantic_candidates = SemanticCandidateRuntime(
            compiled_root / "semantic_candidates"
        )
        self.semantic_data = SemanticDataRuntime(
            compiled_root / "semantic_data"
        )

    def _base_semantic_metrics(self, response):
        return {
            **response.metrics,
            **self.semantic_candidates.last_metrics,
            **self.semantic_data.last_metrics,
        }

    def analyze(self, request: AnalyzeRequest, *, exhaustive_rules: bool = False):
        response = super().analyze(request, exhaustive_rules=exhaustive_rules)
        candidate_available = self.semantic_candidates.available
        approved_available = (
            self.semantic_data.available and self.semantic_data.record_count > 0
        )

        # Preserve the original hot path byte-for-byte when no compiled pack is
        # present. This is the default source checkout and must keep the existing
        # 10 ms stdio contract without no-op graph copies or guard recomputation.
        if not candidate_available and not approved_available:
            return response.model_copy(update={
                "metrics": {
                    **self._base_semantic_metrics(response),
                    "semantic_data_enrichment_ms": 0.0,
                }
            })

        started = perf_counter()
        graph = response.meaning_graph
        if candidate_available:
            graph = self.semantic_candidates.enrich(
                graph,
                tokens=response.tokens,
                original_text=request.original_text,
                conversation_context=request.conversation_context,
                known_entities=request.known_entities,
            )

        # Candidate-only data can add source-backed SenseCandidate values, but
        # cannot alter a selected sense, parameters, tasks, or action safety.
        # Avoid rebuilding the task graph and guard when there are no approved
        # semantic effects to apply.
        if not approved_available:
            semantic_ms = round((perf_counter() - started) * 1000, 3)
            previous_total = float(response.metrics.get("total_ms", 0.0))
            total_ms = round(previous_total + semantic_ms, 3)
            hard_deadline_met = total_ms <= self.settings.hard_deadline_ms
            external_action = (
                request.execution_mode == ExecutionMode.EXTERNAL_ACTION
            )
            overall = response.overall_status
            execution_allowed = response.execution_allowed
            blocked = list(response.blocked_reasons)
            if not hard_deadline_met:
                overall = OverallStatus.PARTIAL
                if external_action:
                    execution_allowed = False
                    blocked = list(dict.fromkeys([*blocked, "TIMEOUT"]))
            return response.model_copy(update={
                "overall_status": overall,
                "meaning_graph": graph,
                "execution_allowed": execution_allowed,
                "blocked_reasons": blocked,
                "metrics": {
                    **self._base_semantic_metrics(response),
                    "semantic_data_enrichment_ms": semantic_ms,
                    "semantic_hash": graph.semantic_hash,
                    "total_ms": total_ms,
                    "elapsed_ms": total_ms,
                    "hard_deadline_met": hard_deadline_met,
                },
            })

        graph = self.semantic_data.enrich(
            graph,
            tokens=response.tokens,
            original_text=request.original_text,
            conversation_context=request.conversation_context,
            known_entities=request.known_entities,
        )
        semantic_ms = round((perf_counter() - started) * 1000, 3)
        task_graph = self.action_tasks.build(graph)
        guard_allowed, guard_blocked, action_closure = self.guard.evaluate(
            graph,
            contradictions=response.contradictions,
            unsupported=response.unsupported_elements,
            timeouts=response.timeouts,
            external_action=request.execution_mode == ExecutionMode.EXTERNAL_ACTION,
        )
        external_action = request.execution_mode == ExecutionMode.EXTERNAL_ACTION
        execution_allowed = (
            response.execution_allowed and guard_allowed
            if external_action
            else True
        )
        blocked = (
            list(dict.fromkeys([
                *response.blocked_reasons,
                *guard_blocked,
            ]))
            if external_action
            else []
        )
        overall = response.overall_status
        if graph.unresolved and overall == OverallStatus.COMPLETE:
            overall = OverallStatus.PARTIAL
        previous_total = float(response.metrics.get("total_ms", 0.0))
        total_ms = round(previous_total + semantic_ms, 3)
        hard_deadline_met = total_ms <= self.settings.hard_deadline_ms
        if not hard_deadline_met:
            overall = OverallStatus.PARTIAL
            if external_action:
                execution_allowed = False
                blocked = list(dict.fromkeys([*blocked, "TIMEOUT"]))
        metrics = {
            **self._base_semantic_metrics(response),
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
            "execution_allowed": execution_allowed,
            "blocked_reasons": blocked,
            "metrics": metrics,
        })
