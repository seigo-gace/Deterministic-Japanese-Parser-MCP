from __future__ import annotations

import pytest
from pydantic import ValidationError

from deterministic_japanese_parser_mcp.interpretation_contracts import (
    FieldEvidenceReference,
    RecoveryCandidateEvidence,
    RecoveryInterpretationEvidence,
    RouterRetrievalLimits,
    RouterTrace,
)
from deterministic_japanese_parser_mcp.models import OriginalSpan


def _limits() -> RouterRetrievalLimits:
    return RouterRetrievalLimits(
        max_candidates_per_lane=8,
        max_total_candidates=32,
        max_recovery_passes=2,
        max_work_ms=20.0,
    )


def _candidate() -> RecoveryCandidateEvidence:
    return RecoveryCandidateEvidence(
        candidate_text="確認してください",
        runtime_record_ids=["CDICT-1"],
        operations=["substitution"],
        recovery_cost=1.0,
        score_components={"reading": 20.0, "syntax": 30.0},
        evidence_ids=["ev-1"],
    )


def _span() -> OriginalSpan:
    return OriginalSpan(start=0, end=8, source_text="確認してくだしあ")


def test_router_trace_requires_selected_lane_to_be_candidate():
    with pytest.raises(ValidationError, match="selected_lanes must be a subset"):
        RouterTrace(
            detected_input_features=["noun"],
            router_decision="noun-route",
            candidate_lanes=["Noun-Entity"],
            selected_lanes=["Syntax-Case-Clause"],
            routing_version="router-v1",
            projection_version="projection-v1",
            retrieval_limits=_limits(),
        )


def test_router_trace_requires_fallback_reason_when_recovery_is_needed():
    with pytest.raises(ValidationError, match="fallback_reason"):
        RouterTrace(
            router_decision="recovery",
            candidate_lanes=["Orthography/Reading"],
            selected_lanes=["Orthography/Reading"],
            recovery_needed=True,
            routing_version="router-v1",
            projection_version="projection-v1",
            retrieval_limits=_limits(),
        )


def test_router_trace_valid_contract_is_inspectable():
    trace = RouterTrace(
        detected_input_features=["oov", "suspicious-segmentation"],
        router_decision="lexical-plus-syntax",
        candidate_lanes=["Orthography/Reading", "Syntax-Case-Clause"],
        selected_lanes=["Orthography/Reading"],
        skipped_lanes=[
            {"lane": "Syntax-Case-Clause", "reason": "no-clause-conflict-yet"}
        ],
        secondary_facets=["domain"],
        fallback_reason="oov",
        recovery_needed=True,
        routing_version="router-v1",
        projection_version="projection-v1",
        retrieval_limits=_limits(),
    )
    assert trace.selected_lanes == ["Orthography/Reading"]
    assert trace.recovery_needed is True


def test_recovery_candidate_requires_runtime_landing_and_evidence():
    with pytest.raises(ValidationError, match="runtime data"):
        RecoveryCandidateEvidence(
            candidate_text="候補",
            operations=["substitution"],
            recovery_cost=1.0,
            evidence_ids=["ev-1"],
        )
    with pytest.raises(ValidationError, match="evidence_ids"):
        RecoveryCandidateEvidence(
            candidate_text="候補",
            runtime_record_ids=["CDICT-1"],
            operations=["substitution"],
            recovery_cost=1.0,
        )


def test_resolved_recovery_requires_candidate_score_margin_and_evidence():
    with pytest.raises(ValidationError, match="below minimum_margin"):
        RecoveryInterpretationEvidence(
            recovery_version="recovery-v1",
            original_span=_span(),
            original_text="確認してくだしあ",
            candidates=[_candidate()],
            selected_candidate="確認してください",
            absolute_score=90.0,
            margin=4.0,
            minimum_score=80.0,
            minimum_margin=5.0,
            decision="RESOLVED",
            evidence_ids=["ev-1"],
        )


def test_unresolved_recovery_must_not_select_candidate():
    with pytest.raises(ValidationError, match="must not select"):
        RecoveryInterpretationEvidence(
            recovery_version="recovery-v1",
            original_span=_span(),
            original_text="確認してくだしあ",
            candidates=[_candidate()],
            selected_candidate="確認してください",
            minimum_score=80.0,
            minimum_margin=5.0,
            decision="AMBIGUOUS",
        )


def test_protected_element_change_cannot_resolve():
    with pytest.raises(ValidationError, match="protected-element"):
        RecoveryInterpretationEvidence(
            recovery_version="recovery-v1",
            original_span=_span(),
            original_text="確認してくだしあ",
            candidates=[_candidate()],
            selected_candidate="確認してください",
            absolute_score=90.0,
            margin=10.0,
            minimum_score=80.0,
            minimum_margin=5.0,
            decision="RESOLVED",
            protected_element_changed=True,
            evidence_ids=["ev-1"],
        )


def test_recovered_action_semantics_fail_external_action_safety():
    value = RecoveryInterpretationEvidence(
        recovery_version="recovery-v1",
        original_span=_span(),
        original_text="確認してくだしあ",
        candidates=[_candidate()],
        selected_candidate="確認してください",
        absolute_score=90.0,
        margin=10.0,
        minimum_score=80.0,
        minimum_margin=5.0,
        decision="RESOLVED",
        changed_action_semantics=True,
        evidence_ids=["ev-1"],
    )
    assert value.external_action_safe is False


def test_field_rights_require_explicit_permission_for_runtime_use():
    with pytest.raises(ValidationError, match="allowed_consumers"):
        FieldEvidenceReference(
            evidence_id="ev-1",
            source_id="src-1",
            source_version="1",
            field_semantics="gloss",
            license_or_rights_lane="public-runtime",
            authority_role="semantic_authority",
            public_runtime_eligible=True,
            allowed_uses=["sense-resolution"],
        )


def test_field_rights_permit_only_explicit_consumer_and_use():
    ref = FieldEvidenceReference(
        evidence_id="ev-1",
        source_id="src-1",
        source_version="1",
        field_semantics="gloss",
        license_or_rights_lane="public-runtime",
        authority_role="semantic_authority",
        public_runtime_eligible=True,
        allowed_consumers=["sense_resolver"],
        allowed_uses=["sense-resolution"],
        forbidden_uses=["training"],
    )
    assert ref.permits(consumer="sense_resolver", use="sense-resolution") is True
    assert ref.permits(consumer="other", use="sense-resolution") is False
    assert ref.permits(consumer="sense_resolver", use="training") is False
