from __future__ import annotations

from deterministic_japanese_parser_mcp.interpretation_contracts import (
    FieldEvidenceReference,
    RouterRetrievalLimits,
    RouterTrace,
)
from deterministic_japanese_parser_mcp.meaning_graph_interpretation import (
    InterpretationAnalyzeResponse,
    InterpretationMeaningGraph,
    attach_interpretation_evidence,
    attach_interpretation_to_response,
    interpretation_evidence_summary,
)
from deterministic_japanese_parser_mcp.models import (
    AnalyzeResponse,
    MeaningGraph,
    OverallStatus,
)


def _trace() -> RouterTrace:
    return RouterTrace(
        detected_input_features=["noun_or_entity_candidate"],
        router_decision="progressive-retrieval",
        candidate_lanes=["Orthography/Reading", "Noun-Entity"],
        selected_lanes=["Orthography/Reading", "Noun-Entity"],
        routing_version="japanese-function-router-v1",
        projection_version="projection-v1",
        retrieval_limits=RouterRetrievalLimits(
            max_candidates_per_lane=32,
            max_total_candidates=128,
            max_recovery_passes=2,
            max_work_ms=25.0,
        ),
    )


def _field_evidence() -> FieldEvidenceReference:
    return FieldEvidenceReference(
        evidence_id="ev-1",
        source_id="source-1",
        source_version="v1",
        field_semantics="reading",
        license_or_rights_lane="test-only",
        authority_role="ranking_evidence",
        allowed_consumers=["parser"],
        allowed_uses=["ranking"],
        public_runtime_eligible=True,
    )


def _semantic_payload(graph: MeaningGraph) -> str:
    return graph.model_dump_json(exclude={"semantic_hash"})


def _response() -> AnalyzeResponse:
    return AnalyzeResponse(
        overall_status=OverallStatus.COMPLETE,
        execution_allowed=True,
        original_text="確認する",
        normalized_text="確認する",
        analysis_path="FAST",
        meaning_graph=MeaningGraph(semantic_hash="stable-hash"),
    )


def test_interpretation_evidence_attaches_without_changing_semantic_identity():
    base = MeaningGraph()
    connected = attach_interpretation_evidence(
        base,
        router_trace=_trace(),
        field_evidence=[_field_evidence()],
    )

    assert isinstance(connected, InterpretationMeaningGraph)
    assert _semantic_payload(connected) == _semantic_payload(base)
    assert connected.router_trace is not None
    assert connected.field_evidence[0].evidence_id == "ev-1"


def test_normal_serialization_keeps_inspectable_interpretation_evidence():
    connected = attach_interpretation_evidence(
        MeaningGraph(),
        router_trace=_trace(),
        field_evidence=[_field_evidence()],
    )

    payload = connected.model_dump(mode="json")
    assert payload["router_trace"]["router_decision"] == "progressive-retrieval"
    assert payload["field_evidence"][0]["authority_role"] == "ranking_evidence"
    assert interpretation_evidence_summary(connected) == {
        "router_trace_present": True,
        "recovery_evidence_count": 0,
        "field_evidence_count": 1,
    }


def test_response_specialization_preserves_evidence_and_existing_hash():
    response = _response()
    connected = attach_interpretation_to_response(
        response,
        router_trace=_trace(),
        field_evidence=[_field_evidence()],
    )

    assert isinstance(connected, InterpretationAnalyzeResponse)
    payload = connected.model_dump(mode="json")
    assert payload["meaning_graph"]["semantic_hash"] == "stable-hash"
    assert payload["meaning_graph"]["router_trace"]["routing_version"] == (
        "japanese-function-router-v1"
    )
    assert payload["meaning_graph"]["field_evidence"][0]["evidence_id"] == "ev-1"


def test_real_semantic_change_still_changes_semantic_identity():
    connected = attach_interpretation_evidence(MeaningGraph(), router_trace=_trace())
    changed = connected.model_copy(
        update={"unresolved": [{"type": "material_semantic_ambiguity"}]}
    )

    assert _semantic_payload(changed) != _semantic_payload(connected)


def test_base_meaning_graph_contract_is_not_mutated_by_attachment():
    base = MeaningGraph()
    connected = attach_interpretation_evidence(base, router_trace=_trace())

    assert "router_trace" not in MeaningGraph.model_fields
    assert base.model_dump() == MeaningGraph().model_dump()
    assert connected.graph_version == "2.3.0"
