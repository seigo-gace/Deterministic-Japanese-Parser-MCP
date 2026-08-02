from time import perf_counter

from .anaphora import AnaphoraResolver
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
        self.bundle = DictionaryBundle(settings.system_dict_dir, settings.user_dict_dir)
        self.tokenizer = JapaneseTokenizer()
        self.rules = RuleEngine(self.bundle.rules)
        self.metaphors = MetaphorMatcher(self.bundle.metaphors)
        self.anaphora = AnaphoraResolver()
        self.tasks = TaskDecomposer(self.bundle.templates)

    def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        started = perf_counter()
        deadline_at = started + request.deadline_ms / 1000
        if len(request.original_text) > self.settings.max_input_length:
            raise ValueError("input exceeds max_input_length")

        context = request.conversation_context[-self.settings.max_context_items :]
        normalized, mapping = normalize_with_map(request.original_text)
        intents, timeouts = self.rules.extract(
            normalized,
            mapping,
            request.original_text,
            deadline_at=deadline_at,
        )

        metaphors = []
        references = []
        if perf_counter() < deadline_at:
            metaphors = self.metaphors.find(normalized, mapping, request.original_text)
        else:
            timeouts.append({"phase": "metaphor_detection", "status": "TIMEOUT"})

        if perf_counter() < deadline_at:
            references = self.anaphora.resolve(
                normalized,
                mapping,
                request.original_text,
                context,
                request.known_entities,
                max_candidates=self.settings.max_candidates,
            )
        else:
            timeouts.append({"phase": "reference_resolution", "status": "TIMEOUT"})

        contradictions = detect(intents, request.protected_elements)
        deep = (
            request.analysis_depth == AnalysisDepth.DEEP
            or bool(metaphors or references or contradictions or timeouts)
        )
        tasks = self.tasks.build(intents, metaphors)
        unresolved = [reference for reference in references if reference.status != ItemStatus.RESOLVED]
        unsupported = []
        if not intents and not metaphors:
            unsupported = [{"text": request.original_text, "status": "UNSUPPORTED"}]

        overall = OverallStatus.COMPLETE
        if contradictions or unresolved or unsupported or timeouts:
            overall = OverallStatus.PARTIAL
        if not intents and not metaphors and not references:
            overall = OverallStatus.FAILED

        blocked: list[str] = []
        if request.execution_mode == ExecutionMode.EXTERNAL_ACTION:
            if contradictions:
                blocked.append("CONTRADICTORY")
            if unresolved:
                blocked.append("AMBIGUOUS_OR_INSUFFICIENT_REFERENCE")
            if unsupported:
                blocked.append("UNSUPPORTED")
            if timeouts:
                blocked.append("TIMEOUT")

        elapsed = (perf_counter() - started) * 1000
        response = AnalyzeResponse(
            overall_status=overall,
            execution_allowed=not blocked,
            blocked_reasons=list(dict.fromkeys(blocked)),
            original_text=request.original_text,
            normalized_text=normalized,
            analysis_path="FAILED" if overall == OverallStatus.FAILED else ("DEEP" if deep else "FAST"),
            tokens=self.tokenizer.tokenize(normalized, mapping, request.original_text),
            intents=intents,
            metaphors=metaphors,
            references=references,
            tasks=tasks,
            ambiguities=[
                reference.model_dump()
                for reference in unresolved
                if reference.status == ItemStatus.AMBIGUOUS
            ],
            missing_information=[
                reference.model_dump()
                for reference in unresolved
                if reference.status == ItemStatus.INSUFFICIENT
            ],
            contradictions=contradictions,
            unsupported_elements=unsupported,
            timeouts=timeouts,
            versions=VERSION,
            metrics={
                "elapsed_ms": round(elapsed, 3),
                "intent_count": len(intents),
                "metaphor_count": len(metaphors),
                "task_count": len(tasks),
                "tokenizer_backend": self.tokenizer.backend,
            },
        )
        if overall != OverallStatus.COMPLETE:
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
        return response
