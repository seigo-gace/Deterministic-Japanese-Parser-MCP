from time import perf_counter

from .anaphora import AnaphoraResolver
from .canonical import Canonicalizer
from .config import SETTINGS, Settings
from .contradictions import detect
from .dictionaries import DictionaryBundle
from .logger import append_log
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
from .rule_engine import RuleEngine
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
        self.anaphora = AnaphoraResolver()
        self.canonicalizer = Canonicalizer(self.bundle.synonyms)
        self.tasks = TaskDecomposer(self.bundle.templates)

    def analyze(
        self,
        request: AnalyzeRequest,
        *,
        exhaustive_rules: bool = False,
    ) -> AnalyzeResponse:
        started = perf_counter()
        deadline_at = started + request.deadline_ms / 1000
        phase_metrics: dict[str, float] = {}

        def run_phase(name: str, function):
            phase_started = perf_counter()
            value = function()
            phase_metrics[f"{name}_ms"] = round(
                (perf_counter() - phase_started) * 1000,
                3,
            )
            return value

        if len(request.original_text) > self.settings.max_input_length:
            raise ValueError("input exceeds max_input_length")

        context = request.conversation_context[
            -self.settings.max_context_items :
        ]
        normalized, mapping = run_phase(
            "normalization",
            lambda: normalize_with_map(request.original_text),
        )

        if exhaustive_rules:
            intents, timeouts = run_phase(
                "intent_extraction",
                lambda: self.rules.extract_exhaustive(
                    normalized,
                    mapping,
                    request.original_text,
                    deadline_at=deadline_at,
                ),
            )
            rule_metrics = {
                "total_rule_count": len(self.rules.compiled),
                "candidate_rule_count": len(self.rules.compiled),
                "indexed_rule_count": (
                    len(self.rules.compiled) - len(self.rules.always_scan)
                ),
                "always_scan_rule_count": len(self.rules.always_scan),
            }
        else:
            intents, timeouts = run_phase(
                "intent_extraction",
                lambda: self.rules.extract(
                    normalized,
                    mapping,
                    request.original_text,
                    deadline_at=deadline_at,
                ),
            )
            rule_metrics = dict(self.rules.last_metrics)

        metaphors = []
        if perf_counter() < deadline_at:
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
        if perf_counter() < deadline_at:
            reference_intents = [
                intent for intent in intents if intent.type == "reference"
            ]
            references = run_phase(
                "reference_resolution",
                lambda: self.anaphora.resolve_intents(
                    reference_intents,
                    context,
                    request.known_entities,
                    max_candidates=self.settings.max_candidates,
                ),
            )
        else:
            timeouts.append({
                "phase": "reference_resolution",
                "status": "TIMEOUT",
            })
            phase_metrics["reference_resolution_ms"] = 0.0

        tasks = run_phase(
            "task_decomposition",
            lambda: self.tasks.build(
                intents,
                metaphors,
                original_text=request.original_text,
            ),
        )
        contradictions = run_phase(
            "contradiction_detection",
            lambda: detect(
                intents,
                request.protected_elements,
                canonicalizer=self.canonicalizer,
            ),
        )
        contradictions.extend(self.tasks.last_cycles)

        tokens = run_phase(
            "tokenization",
            lambda: self.tokenizer.tokenize(
                normalized,
                mapping,
                request.original_text,
            ),
        )

        unresolved_references = [
            reference
            for reference in references
            if reference.status != ItemStatus.RESOLVED
        ]
        unresolved_metaphors = [
            metaphor
            for metaphor in metaphors
            if metaphor.status
            in {ItemStatus.AMBIGUOUS, ItemStatus.INSUFFICIENT}
        ]
        unsupported_metaphors = [
            metaphor
            for metaphor in metaphors
            if metaphor.status == ItemStatus.UNSUPPORTED
        ]
        unsupported = []
        if not intents and not metaphors:
            unsupported = [{
                "text": request.original_text,
                "status": "UNSUPPORTED",
            }]
        unsupported.extend([
            {
                "text": metaphor.span.source_text,
                "expression": metaphor.expression,
                "status": metaphor.status.value,
            }
            for metaphor in unsupported_metaphors
        ])

        overall = OverallStatus.COMPLETE
        if (
            contradictions
            or unresolved_references
            or unresolved_metaphors
            or unsupported
            or timeouts
        ):
            overall = OverallStatus.PARTIAL
        if not intents and not metaphors and not references:
            overall = OverallStatus.FAILED

        blocked: list[str] = []
        if request.execution_mode == ExecutionMode.EXTERNAL_ACTION:
            if contradictions:
                blocked.append("CONTRADICTORY")
            if unresolved_references:
                blocked.append("AMBIGUOUS_OR_INSUFFICIENT_REFERENCE")
            if unresolved_metaphors:
                blocked.append("AMBIGUOUS_OR_INSUFFICIENT_METAPHOR")
            if unsupported:
                blocked.append("UNSUPPORTED")
            if timeouts:
                blocked.append("TIMEOUT")

        deep = (
            request.analysis_depth == AnalysisDepth.DEEP
            or bool(
                metaphors
                or references
                or contradictions
                or unresolved_metaphors
                or timeouts
            )
        )

        metrics = {
            **phase_metrics,
            **rule_metrics,
            **self.metaphors.last_metrics,
            **self.tasks.last_metrics,
            "intent_count": len(intents),
            "metaphor_count": len(metaphors),
            "reference_count": len(references),
            "task_count": len(tasks),
            "tokenizer_backend": self.tokenizer.backend,
            "rule_strategy": (
                "exhaustive" if exhaustive_rules else "indexed"
            ),
        }

        response = AnalyzeResponse(
            overall_status=overall,
            execution_allowed=not blocked,
            blocked_reasons=list(dict.fromkeys(blocked)),
            original_text=request.original_text,
            normalized_text=normalized,
            analysis_path=(
                "FAILED"
                if overall == OverallStatus.FAILED
                else ("DEEP" if deep else "FAST")
            ),
            tokens=tokens,
            intents=intents,
            metaphors=metaphors,
            references=references,
            tasks=tasks,
            ambiguities=[
                item.model_dump()
                for item in [
                    *unresolved_references,
                    *unresolved_metaphors,
                ]
                if item.status == ItemStatus.AMBIGUOUS
            ],
            missing_information=[
                item.model_dump()
                for item in [
                    *unresolved_references,
                    *unresolved_metaphors,
                ]
                if item.status == ItemStatus.INSUFFICIENT
            ],
            contradictions=contradictions,
            unsupported_elements=unsupported,
            timeouts=timeouts,
            versions=VERSION,
            metrics=metrics,
        )

        if overall != OverallStatus.COMPLETE:
            log_started = perf_counter()
            append_log(
                self.settings.log_path,
                {
                    "original_text": request.original_text,
                    "overall_status": overall.value,
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
        else:
            metrics["logging_ms"] = 0.0

        metrics["total_ms"] = round(
            (perf_counter() - started) * 1000,
            3,
        )
        metrics["elapsed_ms"] = metrics["total_ms"]
        return response.model_copy(update={"metrics": metrics})
