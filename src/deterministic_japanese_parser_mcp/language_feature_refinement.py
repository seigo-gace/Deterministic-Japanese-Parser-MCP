from __future__ import annotations

from time import perf_counter
from typing import Callable

from .engine import ParserEngine
from .language_features import LanguageFeatureRuntime
from .models import (
    AnalyzeRequest,
    ItemStatus,
    LanguageFeatureMatch,
    OverallStatus,
)
from .normalizer import normalize_with_map

_INSTALLED = False


def _overlaps(left: LanguageFeatureMatch, right: LanguageFeatureMatch) -> bool:
    return (
        left.source_span.start < right.source_span.end
        and right.source_span.start < left.source_span.end
    )


def _apply_collision_guards(
    runtime: LanguageFeatureRuntime,
    matches: list[LanguageFeatureMatch],
) -> tuple[list[LanguageFeatureMatch], int]:
    """Remove only candidates explicitly suppressed by reviewed guard entries."""
    guards: list[tuple[LanguageFeatureMatch, set[str]]] = []
    for match in matches:
        entry = runtime.entries.get(match.entry_id, {})
        suppressed = set(entry.get("suppress_entry_ids", []))
        if entry.get("emit", True) is False and suppressed:
            guards.append((match, suppressed))

    output: list[LanguageFeatureMatch] = []
    suppressed_count = 0
    for match in matches:
        entry = runtime.entries.get(match.entry_id, {})
        if entry.get("emit", True) is False:
            continue
        blocked = any(
            match.entry_id in suppressed_ids
            and _overlaps(match, guard_match)
            for guard_match, suppressed_ids in guards
        )
        if blocked:
            suppressed_count += 1
            continue
        output.append(match)
    return output, suppressed_count


def install_language_feature_runtime() -> None:
    """Attach the compiled language-feature runtime to ParserEngine.

    The wrapper runs after the existing deterministic engine and semantic
    refinements. It never calls a model or network service. Ambiguous
    action/social features fail closed for external-action requests.
    """
    global _INSTALLED
    if _INSTALLED:
        return
    original_init: Callable = ParserEngine.__init__
    original_analyze: Callable = ParserEngine.analyze

    def __init__(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.language_features = LanguageFeatureRuntime(
            self.settings.system_dict_dir / "compiled/language_features.d"
        )

    def analyze(self, request: AnalyzeRequest, *args, **kwargs):
        response = original_analyze(self, request, *args, **kwargs)
        started = perf_counter()
        normalized, mapping = normalize_with_map(request.original_text)
        raw_matches = self.language_features.analyze(
            normalized,
            mapping,
            request.original_text,
            tokens=response.tokens,
            social_context=request.social_context,
            discourse_state=request.discourse_state,
        )
        matches, collision_suppressed = _apply_collision_guards(
            self.language_features,
            raw_matches,
        )
        metrics = dict(response.metrics)
        metrics.update({
            "language_feature_ms": round(
                (perf_counter() - started) * 1000, 3
            ),
            "language_feature_emitted_match_count": len(matches),
            "language_feature_collision_suppressed_count": collision_suppressed,
            **{
                f"language_feature_{key}": value
                for key, value in self.language_features.last_metrics.items()
            },
        })
        if not matches:
            return response.model_copy(update={"metrics": metrics})

        graph = self.language_features.apply_to_graph(
            response.meaning_graph, matches
        )
        ambiguous = [
            item for item in matches if item.status != ItemStatus.RESOLVED
        ]
        resolved = [
            item for item in matches if item.status == ItemStatus.RESOLVED
        ]
        blocked_reasons = list(response.blocked_reasons)
        execution_allowed = response.execution_allowed
        if request.execution_mode.value == "external_action" and any(
            item.risk_class in {"action", "social"} for item in ambiguous
        ):
            execution_allowed = False
            blocked_reasons = list(dict.fromkeys([
                *blocked_reasons,
                "AMBIGUOUS_LANGUAGE_FEATURE",
            ]))

        unsupported = list(response.unsupported_elements)
        if resolved:
            unsupported = [
                item
                for item in unsupported
                if not (
                    item.get("text") == request.original_text
                    and not item.get("expression")
                )
            ]

        overall = response.overall_status
        if overall == OverallStatus.FAILED and matches:
            if ambiguous:
                overall = OverallStatus.PARTIAL
            else:
                remaining_incomplete = bool(
                    graph.unresolved
                    or unsupported
                    or response.contradictions
                    or response.timeouts
                    or response.missing_information
                )
                overall = (
                    OverallStatus.PARTIAL
                    if remaining_incomplete
                    else OverallStatus.COMPLETE
                )
        elif ambiguous and overall == OverallStatus.COMPLETE:
            overall = OverallStatus.PARTIAL

        versions = dict(response.versions)
        versions["language_feature_asset"] = self.language_features.asset_sha256
        return response.model_copy(update={
            "meaning_graph": graph,
            "overall_status": overall,
            "execution_allowed": execution_allowed,
            "blocked_reasons": blocked_reasons,
            "unsupported_elements": unsupported,
            "analysis_path": "DEEP",
            "versions": versions,
            "metrics": metrics,
        })

    ParserEngine.__init__ = __init__
    ParserEngine.analyze = analyze
    _INSTALLED = True
