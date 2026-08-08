from __future__ import annotations

from time import perf_counter

from .anaphora import AnaphoraResolver
from .canonical import Canonicalizer
from .config import SETTINGS, Settings
from .contradictions import detect
from .dictionaries import DictionaryBundle
from .graph_contradictions import detect_graph
from .graph_guard import GraphGuard
from .logger import append_log
from .lexical_graph import LexicalGraphEnricher
from .meaning_graph import MeaningGraphBuilder
from .metaphor import MetaphorMatcher
from .models import (
    AnalysisDepth,
    AnalyzeRequest,
    AnalyzeResponse,
    ExecutionMode,
    ItemStatus,
    OverallStatus,
)
from .normalizer import normalize_with_map
from .reading_runtime import DeterministicReadingRuntime
from .rule_engine import RuleEngine
from .semantic_data_runtime import SemanticDataRuntime
from .semantic_enrichment import SemanticEnricher
from .task_graph import ActionTaskGraphBuilder
from .tasks import TaskDecomposer
from .tokenizer import JapaneseTokenizer
from .version import VERSION


class ParserEngine:
    def __init__(self, settings: Settings = SETTINGS):
        self.settings = settings
        self.bundle = DictionaryBundle(
            settings.system_dict_dir,
            settings.user_dict_dir,
        )
        self.tokenizer = JapaneseTokenizer()
        self.rules = RuleEngine(
            self.bundle.rules,
            timeout_ms=settings.regex_timeout_ms,
        )
        self.metaphors = MetaphorMatcher(
            self.bundle.metaphors,
            timeout_ms=settings.regex_timeout_ms,
        )
        self.canonicalizer = Canonicalizer(self.bundle.synonyms)
        self.anaphora = AnaphoraResolver(self.canonicalizer)
        self.meaning = MeaningGraphBuilder(
            self.canonicalizer,
            max_graph_nodes=settings.max_graph_nodes,
            max_scope_edges=settings.max_scope_edges,
        )
        self.enricher = SemanticEnricher(
            settings.system_dict_dir / "semantic_profiles.yaml",
            self.canonicalizer,
        )
        self.reading = DeterministicReadingRuntime(
            max_frames=settings.max_graph_nodes,
            max_operators=settings.max_scope_edges,
        )
        self.semantic_data = SemanticDataRuntime(
            settings.system_dict_dir / "compiled" / "semantic_data",
        )
        self.lexical_graph = LexicalGraphEnricher(
            max_nodes=settings.max_graph_nodes,
        )
        self.tasks = TaskDecomposer(self.bundle.templates)
        self.action_tasks = ActionTaskGraphBuilder(self.bundle.templates)
        self.guard = GraphGuard()

    @staticmethod
    def _deduplicate_contradictions(items: list[dict]) -> list[dict]:
        unique: dict[tuple, dict] = {}
        for item in items:
            left = item.get("left", {})
            right = item.get("right", {})
            key = (
                item.get("type"),
                item.get("protected_element"),
                item.get("left_proposition_id"),
                item.get("right_proposition_id"),
                left.get("rule_id"),
                left.get("span", {}).get("start"),
                right.get("rule_id"),
                right.get("span", {}).get("start"),
            )
            unique.setdefault(key, item)
        return list(unique.values())

    @staticmethod
    def _merge_reference_intents(raw_intents, discovered):
        unique = {}
        for item in [*raw_intents, *discovered]:
            key = (
                item.type,
                item.value,
                item.span.start,
                item.span.end,
            )
            current = unique.get(key)
            if current is None or item.priority > current.priority:
                unique[key] = item
        return sorted(
            unique.values(),
            key=lambda item: (
                item.span.start,
                item.span.end,
                -item.priority,
                item.type,
            ),
        )

    def analyze(
        self,
        request: AnalyzeRequest,
        *,
        exhaustive_rules: bool = False,
    ) -> AnalyzeResponse:
        started = perf_counter()
        effective_deadline_ms = min(
            request.deadline_ms,
            self.settings.hard_deadline_ms,
        )
        deadline_at = started + effective_deadline_ms / 1000
        phase_metrics: dict[str, float | int | str] = {}

        def run_phase(name: str, function):
            phase_started = perf_counter()
            value = function()
            phase_metrics[f"{name}_ms"] = round(
                (perf_counter() - phase_started) * 1000,
                3,
            )
            return value

        def deadline_remaining() -> bool:
            return perf_counter() < deadline_at

        if len(request.original_text) > self.settings.max_input_length:
            raise ValueError("input exceeds max_input_length")

        context = request.conversation_context[
            -self.settings.max_context_items :
        ]
        normalized, mapping = run_phase(
            "normalization",
            lambda: normalize_with_map(request.original_text),
        )
        tokens = run_phase(
            "tokenization",
            lambda: self.tokenizer.tokenize(
                normalized,
                mapping,
                request.original_text,
            ),
        )

        extractor = (
            self.rules.extract_exhaustive
            if exhaustive_rules
            else self.rules.extract
        )
        raw_intents, timeouts = run_phase(
            "intent_candidate_detection",
            lambda: extractor(
                normalized,
                mapping,
                request.original_text,
                deadline_at=deadline_at,
            ),
        )
        discovered_references = self.anaphora.discover(
            normalized,
            mapping,
            request.original_text,
        )
        raw_intents = self._merge_reference_intents(
            raw_intents,
            discovered_references,
        )
        rule_metrics = (
            {
                "total_rule_count": len(self.rules.compiled),
                "candidate_rule_count": len(self.rules.compiled),
                "indexed_rule_count": (
                    len(self.rules.compiled) - len(self.rules.always_scan)
                ),
                "always_scan_rule_count": len(self.rules.always_scan),
            }
            if exhaustive_rules
            else dict(self.rules.last_metrics)
        )

        metaphors = []
        if deadline_remaining():
            metaphors = run_phase(
                "metaphor_detection",
                lambda: self.metaphors.find(
                    normalized,
                    mapping,
                    request.original_text,
                ),
            )
            timeouts.extend(self.metaphors.last_timeouts)
        else:
            timeouts.append({
                "phase": "metaphor_detection",
                "status": "TIMEOUT",
            })
            phase_metrics["metaphor_detection_ms"] = 0.0

        references = []
        if deadline_remaining():
            reference_intents = [
                item
                for item in raw_intents
                if item.type == "reference"
            ]
            current_mentions = self.anaphora.mentions_from_intents(
                raw_intents
            )
            references = run_phase(
                "reference_resolution",
                lambda: self.anaphora.resolve_intents(
                    reference_intents,
                    context,
                    request.known_entities,
                    max_candidates=self.settings.max_candidates,
                    current_mentions=current_mentions,
                ),
            )
        else:
            timeouts.append({
                "phase": "reference_resolution",
                "status": "TIMEOUT",
            })
            phase_metrics["reference_resolution_ms"] = 0.0

        meaning_graph = run_phase(
            "meaning_graph",
            lambda: self.meaning.build(
                original_text=request.original_text,
                normalized_text=normalized,
                tokens=tokens,
                intents=raw_intents,
                references=references,
                metaphors=metaphors,
                conversation_context=context,
                known_entities=request.known_entities,
                update_hash=False,
            ),
        )
        if deadline_remaining():
            meaning_graph = run_phase(
                "semantic_enrichment",
                lambda: self.enricher.enrich(
                    meaning_graph,
                    original_text=request.original_text,
                    tokens=tokens,
                    metaphors=metaphors,
                    conversation_context=context,
                    known_entities=request.known_entities,
                    update_hash=False,
                ),
            )
        else:
            timeouts.append({
                "phase": "semantic_enrichment",
                "status": "TIMEOUT",
            })
            phase_metrics["semantic_enrichment_ms"] = 0.0

        if deadline_remaining():
            meaning_graph = run_phase(
                "reading_analysis",
                lambda: self.reading.enrich(
                    meaning_graph,
                    tokens=tokens,
                    original_text=request.original_text,
                    update_hash=False,
                ),
            )
        else:
            timeouts.append({
                "phase": "reading_analysis",
                "status": "TIMEOUT",
            })
            phase_metrics["reading_analysis_ms"] = 0.0
            self.reading.last_metrics = {
                "reading_predicate_frame_count": 0,
                "reading_dependency_arc_count": 0,
                "reading_scope_operator_count": 0,
                "reading_attribution_frame_count": 0,
                "reading_discourse_relation_count": 0,
                "reading_unresolved_count": 0,
            }

        if deadline_remaining():
            meaning_graph = run_phase(
                "approved_semantic_data",
                lambda: self.semantic_data.enrich(
                    meaning_graph,
                    tokens=tokens,
                    original_text=request.original_text,
                    conversation_context=context,
                    known_entities=request.known_entities,
                    update_hash=False,
                ),
            )
        else:
            timeouts.append({
                "phase": "approved_semantic_data",
                "status": "TIMEOUT",
            })
            phase_metrics["approved_semantic_data_ms"] = 0.0
            self.semantic_data.last_metrics = {
                "semantic_pack_available": int(self.semantic_data.available),
                "semantic_pack_match_count": 0,
                "semantic_pack_resolved_count": 0,
                "semantic_pack_ambiguous_count": 0,
            }

        if deadline_remaining():
            meaning_graph = run_phase(
                "lexical_graph_enrichment",
                lambda: self.lexical_graph.enrich(
                    meaning_graph,
                    tokens=tokens,
                    original_text=request.original_text,
                    conversation_context=context,
                    known_entities=request.known_entities,
                ),
            )
        else:
            phase_metrics["lexical_graph_enrichment_ms"] = 0.0
            self.lexical_graph.last_metrics = {
                "lexical_node_count": 0,
                "resolved_lexical_node_count": 0,
                "ambiguous_lexical_node_count": 0,
                "lexical_candidate_count": 0,
                "lexical_node_limit_skip_count": 0,
                "lexical_context_registry_used": 0,
            }

        intents = self.meaning.emit_legacy_intents(
            meaning_graph,
            raw_intents,
        )
        tasks = run_phase(
            "legacy_task_view",
            lambda: self.tasks.build(
                intents,
                metaphors,
                original_text=request.original_text,
            ),
        )
        task_graph = run_phase(
            "action_task_graph",
            lambda: self.action_tasks.build(meaning_graph),
        )

        contradictions = self._deduplicate_contradictions([
            *run_phase(
                "legacy_contradiction_view",
                lambda: detect(
                    intents,
                    request.protected_elements,
                    canonicalizer=self.canonicalizer,
                ),
            ),
            *run_phase(
                "graph_contradiction_detection",
                lambda: detect_graph(
                    meaning_graph,
                    request.protected_elements,
                    canonicalizer=self.canonicalizer,
                ),
            ),
            *self.tasks.last_cycles,
            *self.action_tasks.last_cycles,
        ])

        unresolved_references = [
            item
            for item in references
            if item.status != ItemStatus.RESOLVED
        ]
        unresolved_metaphors = [
            item
            for item in metaphors
            if item.status in {
                ItemStatus.AMBIGUOUS,
                ItemStatus.INSUFFICIENT,
            }
        ]
        unsupported = []
        if not meaning_graph.propositions and not metaphors:
            unsupported.append({
                "text": request.original_text,
                "status": ItemStatus.UNSUPPORTED.value,
            })
        unsupported.extend([
            {
                "text": item.span.source_text,
                "expression": item.expression,
                "status": item.status.value,
            }
            for item in metaphors
            if item.status == ItemStatus.UNSUPPORTED
        ])

        execution_allowed, blocked, action_closure = self.guard.evaluate(
            meaning_graph,
            contradictions=contradictions,
            unsupported=unsupported,
            timeouts=timeouts,
            external_action=(
                request.execution_mode == ExecutionMode.EXTERNAL_ACTION
            ),
        )

        overall = OverallStatus.COMPLETE
        if (
            contradictions
            or unresolved_references
            or unresolved_metaphors
            or meaning_graph.unresolved
            or unsupported
            or timeouts
        ):
            overall = OverallStatus.PARTIAL
        if (
            not meaning_graph.propositions
            and not metaphors
            and not references
        ):
            overall = OverallStatus.FAILED

        elapsed_before_response = (perf_counter() - started) * 1000
        if elapsed_before_response > self.settings.hard_deadline_ms:
            timeouts.append({
                "phase": "complete_response",
                "status": ItemStatus.TIMEOUT.value,
                "elapsed_ms": round(elapsed_before_response, 3),
                "hard_deadline_ms": self.settings.hard_deadline_ms,
            })
            overall = OverallStatus.PARTIAL
            if request.execution_mode == ExecutionMode.EXTERNAL_ACTION:
                execution_allowed = False
                blocked = list(dict.fromkeys([*blocked, "TIMEOUT"]))

        quality = meaning_graph.quality_annotations
        deep = (
            request.analysis_depth == AnalysisDepth.DEEP
            or bool(
                metaphors
                or references
                or contradictions
                or meaning_graph.scope_edges
                or meaning_graph.unresolved
                or timeouts
                or quality.get("resolved_senses")
                or quality.get("inferred_arguments")
                or quality.get("pragmatic_acts")
                or quality.get("discourse_edges")
                or self.reading.last_metrics.get("reading_scope_operator_count")
                or self.reading.last_metrics.get("reading_discourse_relation_count")
            )
        )
        metrics = {
            **phase_metrics,
            **rule_metrics,
            **self.metaphors.last_metrics,
            **self.enricher.last_metrics,
            **self.reading.last_metrics,
            **self.semantic_data.last_metrics,
            **self.lexical_graph.last_metrics,
            **self.tasks.last_metrics,
            **self.action_tasks.last_metrics,
            "intent_count": len(intents),
            "metaphor_count": len(metaphors),
            "reference_count": len(references),
            "legacy_task_count": len(tasks),
            "action_task_count": len(task_graph.tasks),
            "entity_count": len(meaning_graph.entities),
            "clause_count": len(meaning_graph.clauses),
            "proposition_count": len(meaning_graph.propositions),
            "meaning_graph_lexical_node_count": len(
                meaning_graph.lexical_nodes
            ),
            "scope_edge_count": len(meaning_graph.scope_edges),
            "action_relevance_node_count": len(action_closure),
            "tokenizer_backend": self.tokenizer.backend,
            "rule_strategy": (
                "exhaustive" if exhaustive_rules else "indexed"
            ),
            "requested_deadline_ms": request.deadline_ms,
            "effective_deadline_ms": effective_deadline_ms,
            "target_latency_ms": self.settings.target_latency_ms,
            "hard_deadline_ms": self.settings.hard_deadline_ms,
            "semantic_hash": meaning_graph.semantic_hash,
        }
        graph_ambiguities = [
            item
            for item in meaning_graph.unresolved
            if item.get("status") == ItemStatus.AMBIGUOUS.value
        ]
        graph_missing = [
            item
            for item in meaning_graph.unresolved
            if item.get("status") == ItemStatus.INSUFFICIENT.value
        ]
        response = AnalyzeResponse(
            overall_status=overall,
            execution_allowed=(
                execution_allowed
                if request.execution_mode == ExecutionMode.EXTERNAL_ACTION
                else True
            ),
            blocked_reasons=(
                blocked
                if request.execution_mode == ExecutionMode.EXTERNAL_ACTION
                else []
            ),
            original_text=request.original_text,
            normalized_text=normalized,
            analysis_path=(
                "FAILED"
                if overall == OverallStatus.FAILED
                else ("DEEP" if deep else "FAST")
            ),
            tokens=tokens,
            meaning_graph=meaning_graph,
            task_graph=task_graph,
            intents=intents,
            metaphors=metaphors,
            references=references,
            tasks=tasks,
            ambiguities=[
                *[
                    item.model_dump()
                    for item in [
                        *unresolved_references,
                        *unresolved_metaphors,
                    ]
                    if item.status == ItemStatus.AMBIGUOUS
                ],
                *graph_ambiguities,
            ],
            missing_information=[
                *[
                    item.model_dump()
                    for item in [
                        *unresolved_references,
                        *unresolved_metaphors,
                    ]
                    if item.status == ItemStatus.INSUFFICIENT
                ],
                *graph_missing,
            ],
            contradictions=contradictions,
            unsupported_elements=unsupported,
            timeouts=timeouts,
            versions=VERSION,
            metrics=metrics,
        )

        if overall != OverallStatus.COMPLETE and deadline_remaining():
            log_started = perf_counter()
            append_log(
                self.settings.log_path,
                {
                    "original_text": request.original_text,
                    "overall_status": overall.value,
                    "semantic_hash": meaning_graph.semantic_hash,
                    "ambiguities": response.ambiguities,
                    "missing_information": response.missing_information,
                    "unsupported_elements": unsupported,
                    "contradictions": contradictions,
                    "timeouts": timeouts,
                },
            )
            metrics["logging_ms"] = round(
                (perf_counter() - log_started) * 1000,
                3,
            )
            metrics["logging_skipped_deadline"] = 0
        else:
            metrics["logging_ms"] = 0.0
            metrics["logging_skipped_deadline"] = int(
                overall != OverallStatus.COMPLETE
            )

        total_ms = round((perf_counter() - started) * 1000, 3)
        metrics["total_ms"] = total_ms
        metrics["elapsed_ms"] = total_ms
        metrics["target_met"] = (
            total_ms <= self.settings.target_latency_ms
        )
        metrics["hard_deadline_met"] = (
            total_ms <= self.settings.hard_deadline_ms
        )
        if total_ms > self.settings.hard_deadline_ms:
            final_blocked = response.blocked_reasons
            if request.execution_mode == ExecutionMode.EXTERNAL_ACTION:
                final_blocked = list(dict.fromkeys([
                    *final_blocked,
                    "TIMEOUT",
                ]))
            response = response.model_copy(update={
                "overall_status": OverallStatus.PARTIAL,
                "execution_allowed": (
                    False
                    if request.execution_mode == ExecutionMode.EXTERNAL_ACTION
                    else response.execution_allowed
                ),
                "blocked_reasons": final_blocked,
                "timeouts": [
                    *response.timeouts,
                    {
                        "phase": "response_transfer_ready",
                        "status": ItemStatus.TIMEOUT.value,
                        "elapsed_ms": total_ms,
                        "hard_deadline_ms": self.settings.hard_deadline_ms,
                    },
                ],
            })
        return response.model_copy(update={"metrics": metrics})
