from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Callable, Literal, Protocol, Sequence

from .interpretation_contracts import (
    FieldEvidenceReference,
    JapaneseFunctionLane,
    RouterTrace,
)
from .models import Token
from .retrieval_router import RetrievalResult, RetrievalRouter


RetrievalStage = Literal["essential", "deep"]


@dataclass(frozen=True)
class RetrievedEvidence:
    """One inspectable evidence item returned by an existing evidence source."""

    lane: JapaneseFunctionLane
    record_id: str
    reference: FieldEvidenceReference
    stage: RetrievalStage


class EvidenceLaneProvider(Protocol):
    """Adapter contract for an existing source; it is not a new meaning authority."""

    lane: JapaneseFunctionLane
    stage: RetrievalStage

    def retrieve(
        self,
        tokens: Sequence[Token],
        *,
        max_candidates: int,
        consumer: str,
        use: str,
    ) -> Sequence[RetrievedEvidence]: ...


@dataclass(frozen=True)
class ProgressiveRetrievalTrace:
    selected_lanes: tuple[JapaneseFunctionLane, ...]
    lexical_token_count: int
    lexical_candidate_count: int
    evidence_count: int
    attempted_providers: tuple[str, ...]
    skipped_providers: tuple[str, ...]
    denied_evidence_ids: tuple[str, ...]
    stopped_after_essential: bool
    candidate_budget_exhausted: bool
    time_budget_exhausted: bool
    complete: bool


@dataclass(frozen=True)
class ProgressiveRetrievalResult:
    lexical_results: tuple[RetrievalResult, ...]
    evidence: tuple[RetrievedEvidence, ...]
    trace: ProgressiveRetrievalTrace


EvidenceSufficiencyProbe = Callable[
    [tuple[RetrievalResult, ...], tuple[RetrievedEvidence, ...]],
    bool,
]


class ProgressiveContextEvidenceRetriever:
    """Retrieve only routed evidence, progressively and with fail-closed bounds.

    Existing ``RetrievalRouter`` remains the lexical retrieval authority. This
    class only orchestrates when existing evidence sources are consulted. It
    does not choose a sense, create a MeaningGraph proposition, or turn an
    evidence/ranking field into semantic authority.
    """

    def __init__(
        self,
        lexical_router: RetrievalRouter,
        providers: Sequence[EvidenceLaneProvider] = (),
        *,
        clock_ms: Callable[[], float] | None = None,
    ) -> None:
        self.lexical_router = lexical_router
        self.providers = tuple(providers)
        self.clock_ms = clock_ms or (lambda: monotonic() * 1000.0)

    @staticmethod
    def _provider_key(provider: EvidenceLaneProvider) -> str:
        return f"{provider.stage}:{provider.lane}"

    @staticmethod
    def _filter_permitted(
        values: Sequence[RetrievedEvidence],
        *,
        lane: JapaneseFunctionLane,
        stage: RetrievalStage,
        consumer: str,
        use: str,
        max_candidates: int,
    ) -> tuple[list[RetrievedEvidence], list[str]]:
        accepted: list[RetrievedEvidence] = []
        denied: list[str] = []
        seen: set[tuple[str, str]] = set()
        for value in values:
            if value.lane != lane or value.stage != stage:
                # A provider cannot smuggle evidence across its registered lane
                # or retrieval depth.
                denied.append(value.reference.evidence_id)
                continue
            if not value.reference.permits(consumer=consumer, use=use):
                denied.append(value.reference.evidence_id)
                continue
            key = (value.record_id, value.reference.evidence_id)
            if key in seen:
                continue
            seen.add(key)
            accepted.append(value)
            if len(accepted) >= max_candidates:
                break
        return accepted, denied

    def retrieve(
        self,
        *,
        tokens: Sequence[Token],
        router_trace: RouterTrace,
        source_roles: Sequence[str],
        consumer: str,
        use: str,
        evidence_sufficient: EvidenceSufficiencyProbe,
    ) -> ProgressiveRetrievalResult:
        """Run lexical -> essential evidence -> optional deep evidence.

        The caller owns the semantic sufficiency decision. If the candidate or
        time budget is exhausted before the requested work completes, ``complete``
        is false; partial retrieval is never promoted to a completed result.
        """
        start_ms = self.clock_ms()
        limits = router_trace.retrieval_limits
        selected = tuple(router_trace.selected_lanes)
        selected_set = set(selected)
        attempted: list[str] = []
        skipped: list[str] = []
        denied: list[str] = []
        evidence: list[RetrievedEvidence] = []
        lexical_results: list[RetrievalResult] = []
        candidate_count = 0
        candidate_budget_exhausted = False
        time_budget_exhausted = False

        def timed_out() -> bool:
            return (self.clock_ms() - start_ms) > limits.max_work_ms

        # Reuse the existing purpose/general/reading lexical router rather than
        # introducing another dictionary reader.
        for token in tokens:
            if timed_out():
                time_budget_exhausted = True
                break
            remaining = limits.max_total_candidates - candidate_count
            if remaining <= 0:
                candidate_budget_exhausted = True
                break
            per_call = min(limits.max_candidates_per_lane, remaining)
            result = self.lexical_router.retrieve_token(
                token,
                source_roles=list(source_roles),
                max_candidates=per_call,
            )
            lexical_results.append(result)
            candidate_count += len(result.candidates)

        lexical_complete = len(lexical_results) == len(tokens)
        if not lexical_complete:
            return ProgressiveRetrievalResult(
                lexical_results=tuple(lexical_results),
                evidence=(),
                trace=ProgressiveRetrievalTrace(
                    selected_lanes=selected,
                    lexical_token_count=len(lexical_results),
                    lexical_candidate_count=candidate_count,
                    evidence_count=0,
                    attempted_providers=(),
                    skipped_providers=(),
                    denied_evidence_ids=(),
                    stopped_after_essential=False,
                    candidate_budget_exhausted=candidate_budget_exhausted,
                    time_budget_exhausted=time_budget_exhausted,
                    complete=False,
                ),
            )

        providers_by_stage: dict[RetrievalStage, list[EvidenceLaneProvider]] = {
            "essential": [],
            "deep": [],
        }
        for provider in self.providers:
            key = self._provider_key(provider)
            if provider.lane not in selected_set:
                skipped.append(f"{key}:lane_not_selected")
                continue
            if provider.stage not in providers_by_stage:
                raise ValueError(f"invalid evidence provider stage: {provider.stage}")
            providers_by_stage[provider.stage].append(provider)

        def run_stage(stage: RetrievalStage) -> bool:
            nonlocal candidate_count, candidate_budget_exhausted, time_budget_exhausted
            for provider in providers_by_stage[stage]:
                if timed_out():
                    time_budget_exhausted = True
                    return False
                remaining = limits.max_total_candidates - candidate_count
                if remaining <= 0:
                    candidate_budget_exhausted = True
                    return False
                per_call = min(limits.max_candidates_per_lane, remaining)
                attempted.append(self._provider_key(provider))
                # Rights context is passed to the source adapter so a compliant
                # provider can avoid loading forbidden fields in the first place.
                # The orchestrator still verifies every returned reference.
                values = provider.retrieve(
                    tokens,
                    max_candidates=per_call,
                    consumer=consumer,
                    use=use,
                )
                if len(values) > per_call:
                    raise ValueError(
                        f"evidence provider exceeded candidate bound: {self._provider_key(provider)}"
                    )
                # Retrieval work consumes budget even when a returned field is
                # later rejected by rights/provenance validation.
                candidate_count += len(values)
                accepted, rejected = self._filter_permitted(
                    values,
                    lane=provider.lane,
                    stage=stage,
                    consumer=consumer,
                    use=use,
                    max_candidates=per_call,
                )
                denied.extend(rejected)
                evidence.extend(accepted)
            return True

        essential_complete = run_stage("essential")
        if not essential_complete:
            return ProgressiveRetrievalResult(
                lexical_results=tuple(lexical_results),
                evidence=tuple(evidence),
                trace=ProgressiveRetrievalTrace(
                    selected_lanes=selected,
                    lexical_token_count=len(lexical_results),
                    lexical_candidate_count=sum(len(item.candidates) for item in lexical_results),
                    evidence_count=len(evidence),
                    attempted_providers=tuple(attempted),
                    skipped_providers=tuple(skipped),
                    denied_evidence_ids=tuple(sorted(set(denied))),
                    stopped_after_essential=False,
                    candidate_budget_exhausted=candidate_budget_exhausted,
                    time_budget_exhausted=time_budget_exhausted,
                    complete=False,
                ),
            )

        lexical_tuple = tuple(lexical_results)
        evidence_tuple = tuple(evidence)
        if evidence_sufficient(lexical_tuple, evidence_tuple):
            return ProgressiveRetrievalResult(
                lexical_results=lexical_tuple,
                evidence=evidence_tuple,
                trace=ProgressiveRetrievalTrace(
                    selected_lanes=selected,
                    lexical_token_count=len(lexical_results),
                    lexical_candidate_count=sum(len(item.candidates) for item in lexical_results),
                    evidence_count=len(evidence),
                    attempted_providers=tuple(attempted),
                    skipped_providers=tuple(skipped),
                    denied_evidence_ids=tuple(sorted(set(denied))),
                    stopped_after_essential=True,
                    candidate_budget_exhausted=False,
                    time_budget_exhausted=False,
                    complete=True,
                ),
            )

        deep_complete = run_stage("deep")
        complete = deep_complete and not candidate_budget_exhausted and not time_budget_exhausted
        return ProgressiveRetrievalResult(
            lexical_results=lexical_tuple,
            evidence=tuple(evidence),
            trace=ProgressiveRetrievalTrace(
                selected_lanes=selected,
                lexical_token_count=len(lexical_results),
                lexical_candidate_count=sum(len(item.candidates) for item in lexical_results),
                evidence_count=len(evidence),
                attempted_providers=tuple(attempted),
                skipped_providers=tuple(skipped),
                denied_evidence_ids=tuple(sorted(set(denied))),
                stopped_after_essential=False,
                candidate_budget_exhausted=candidate_budget_exhausted,
                time_budget_exhausted=time_budget_exhausted,
                complete=complete,
            ),
        )
