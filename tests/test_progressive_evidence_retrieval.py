from types import SimpleNamespace

from deterministic_japanese_parser_mcp.interpretation_contracts import (
    FieldEvidenceReference,
    RouterRetrievalLimits,
    RouterTrace,
)
from deterministic_japanese_parser_mcp.models import OriginalSpan, Token
from deterministic_japanese_parser_mcp.progressive_evidence_retrieval import (
    ProgressiveContextEvidenceRetriever,
    RetrievedEvidence,
)


def _token(text="橋"):
    return Token(
        surface=text,
        normalized=text,
        reading="ハシ",
        pos=["名詞", "普通名詞", "一般"],
        span=OriginalSpan(start=0, end=len(text), source_text=text),
    )


def _trace(*, selected=None, total=16, per_lane=8, work_ms=25.0):
    selected = selected or ["Orthography/Reading", "Noun-Entity"]
    return RouterTrace(
        router_decision="progressive-retrieval",
        candidate_lanes=list(selected),
        selected_lanes=list(selected),
        routing_version="router-v1",
        projection_version="projection-v1",
        retrieval_limits=RouterRetrievalLimits(
            max_candidates_per_lane=per_lane,
            max_total_candidates=total,
            max_recovery_passes=2,
            max_work_ms=work_ms,
        ),
    )


def _reference(
    evidence_id,
    *,
    consumer="sense_resolver",
    use="ranking",
    eligible=True,
):
    return FieldEvidenceReference(
        evidence_id=evidence_id,
        source_id=f"source:{evidence_id}",
        source_version="v1",
        field_semantics="test-evidence",
        license_or_rights_lane="test",
        authority_role="ranking_evidence",
        allowed_consumers=[consumer] if eligible else ["other_consumer"],
        allowed_uses=[use] if eligible else ["other_use"],
        public_runtime_eligible=True,
    )


class FakeLexicalRouter:
    def __init__(self, candidate_count=1):
        self.candidate_count = candidate_count
        self.calls = []

    def retrieve_token(self, token, *, source_roles, max_candidates):
        self.calls.append((token.surface, tuple(source_roles), max_candidates))
        candidates = tuple(
            SimpleNamespace(record_id=f"lex-{token.surface}-{index}")
            for index in range(min(self.candidate_count, max_candidates))
        )
        return SimpleNamespace(candidates=candidates)


class FakeProvider:
    def __init__(self, lane, stage, values):
        self.lane = lane
        self.stage = stage
        self.values = list(values)
        self.calls = []

    def retrieve(self, tokens, *, max_candidates):
        self.calls.append((tuple(token.surface for token in tokens), max_candidates))
        return self.values[:max_candidates]


def _evidence(evidence_id, *, lane="Noun-Entity", stage="essential", eligible=True):
    return RetrievedEvidence(
        lane=lane,
        record_id=f"record:{evidence_id}",
        reference=_reference(evidence_id, eligible=eligible),
        stage=stage,
    )


def test_selected_essential_evidence_stops_before_deep_when_sufficient():
    lexical = FakeLexicalRouter()
    essential = FakeProvider(
        "Noun-Entity",
        "essential",
        [_evidence("essential")],
    )
    deep = FakeProvider(
        "Noun-Entity",
        "deep",
        [_evidence("deep", stage="deep")],
    )
    unselected = FakeProvider(
        "Document Structure",
        "essential",
        [_evidence("unselected", lane="Document Structure")],
    )
    retriever = ProgressiveContextEvidenceRetriever(
        lexical,
        [essential, deep, unselected],
        clock_ms=lambda: 0.0,
    )

    result = retriever.retrieve(
        tokens=[_token()],
        router_trace=_trace(),
        source_roles=["lexical-definition"],
        consumer="sense_resolver",
        use="ranking",
        evidence_sufficient=lambda lexical_results, evidence: bool(evidence),
    )

    assert [item.reference.evidence_id for item in result.evidence] == ["essential"]
    assert essential.calls
    assert not deep.calls
    assert not unselected.calls
    assert result.trace.stopped_after_essential is True
    assert result.trace.complete is True
    assert "essential:Document Structure:lane_not_selected" in result.trace.skipped_providers
    assert lexical.calls == [("橋", ("lexical-definition",), 8)]


def test_deep_context_runs_only_when_essential_is_insufficient():
    lexical = FakeLexicalRouter()
    essential = FakeProvider(
        "Noun-Entity",
        "essential",
        [_evidence("essential")],
    )
    deep = FakeProvider(
        "Noun-Entity",
        "deep",
        [_evidence("deep", stage="deep")],
    )
    retriever = ProgressiveContextEvidenceRetriever(
        lexical,
        [essential, deep],
        clock_ms=lambda: 0.0,
    )

    result = retriever.retrieve(
        tokens=[_token()],
        router_trace=_trace(),
        source_roles=["lexical-definition"],
        consumer="sense_resolver",
        use="ranking",
        evidence_sufficient=lambda lexical_results, evidence: False,
    )

    assert [item.reference.evidence_id for item in result.evidence] == [
        "essential",
        "deep",
    ]
    assert essential.calls and deep.calls
    assert result.trace.stopped_after_essential is False
    assert result.trace.complete is True


def test_field_rights_fail_closed_and_do_not_become_evidence():
    lexical = FakeLexicalRouter()
    provider = FakeProvider(
        "Noun-Entity",
        "essential",
        [
            _evidence("allowed"),
            _evidence("denied", eligible=False),
        ],
    )
    retriever = ProgressiveContextEvidenceRetriever(
        lexical,
        [provider],
        clock_ms=lambda: 0.0,
    )

    result = retriever.retrieve(
        tokens=[_token()],
        router_trace=_trace(),
        source_roles=["lexical-definition"],
        consumer="sense_resolver",
        use="ranking",
        evidence_sufficient=lambda lexical_results, evidence: True,
    )

    assert [item.reference.evidence_id for item in result.evidence] == ["allowed"]
    assert result.trace.denied_evidence_ids == ("denied",)


def test_provider_cannot_smuggle_evidence_from_another_lane():
    lexical = FakeLexicalRouter()
    provider = FakeProvider(
        "Noun-Entity",
        "essential",
        [_evidence("wrong-lane", lane="Document Structure")],
    )
    retriever = ProgressiveContextEvidenceRetriever(
        lexical,
        [provider],
        clock_ms=lambda: 0.0,
    )

    result = retriever.retrieve(
        tokens=[_token()],
        router_trace=_trace(),
        source_roles=[],
        consumer="sense_resolver",
        use="ranking",
        evidence_sufficient=lambda lexical_results, evidence: True,
    )

    assert result.evidence == ()
    assert result.trace.denied_evidence_ids == ("wrong-lane",)


def test_candidate_budget_exhaustion_is_not_reported_complete():
    lexical = FakeLexicalRouter(candidate_count=1)
    retriever = ProgressiveContextEvidenceRetriever(
        lexical,
        [],
        clock_ms=lambda: 0.0,
    )

    result = retriever.retrieve(
        tokens=[_token("橋"), _token("箸")],
        router_trace=_trace(total=1, per_lane=1),
        source_roles=[],
        consumer="sense_resolver",
        use="ranking",
        evidence_sufficient=lambda lexical_results, evidence: True,
    )

    assert len(result.lexical_results) == 1
    assert result.trace.candidate_budget_exhausted is True
    assert result.trace.complete is False
    assert result.evidence == ()


def test_time_budget_exhaustion_is_fail_closed():
    class Clock:
        def __init__(self):
            self.values = iter([0.0, 2.0])

        def __call__(self):
            return next(self.values, 2.0)

    lexical = FakeLexicalRouter()
    retriever = ProgressiveContextEvidenceRetriever(
        lexical,
        [],
        clock_ms=Clock(),
    )

    result = retriever.retrieve(
        tokens=[_token()],
        router_trace=_trace(work_ms=1.0),
        source_roles=[],
        consumer="sense_resolver",
        use="ranking",
        evidence_sufficient=lambda lexical_results, evidence: True,
    )

    assert result.lexical_results == ()
    assert result.trace.time_budget_exhausted is True
    assert result.trace.complete is False


def test_evidence_candidate_cap_is_shared_with_lexical_work():
    lexical = FakeLexicalRouter(candidate_count=2)
    provider = FakeProvider(
        "Noun-Entity",
        "essential",
        [_evidence("e1"), _evidence("e2"), _evidence("e3")],
    )
    retriever = ProgressiveContextEvidenceRetriever(
        lexical,
        [provider],
        clock_ms=lambda: 0.0,
    )

    result = retriever.retrieve(
        tokens=[_token()],
        router_trace=_trace(total=3, per_lane=3),
        source_roles=[],
        consumer="sense_resolver",
        use="ranking",
        evidence_sufficient=lambda lexical_results, evidence: True,
    )

    assert len(result.lexical_results[0].candidates) == 2
    assert [item.reference.evidence_id for item in result.evidence] == ["e1"]
    assert provider.calls[0][1] == 1
