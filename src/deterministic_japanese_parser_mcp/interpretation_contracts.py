from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from .models import OriginalSpan


JAPANESE_FUNCTION_LANES = (
    "Orthography/Reading",
    "Noun-Entity",
    "Predicate-Inflection",
    "Function Words",
    "Connective-Modifier",
    "Onomatopoeia",
    "Multiword",
    "Syntax-Case-Clause",
    "Sense-Semantic Relation",
    "Usage-Context-Pragmatics",
    "Document Structure",
    "Evidence-Provenance-Rights",
)
JapaneseFunctionLane = Literal[
    "Orthography/Reading",
    "Noun-Entity",
    "Predicate-Inflection",
    "Function Words",
    "Connective-Modifier",
    "Onomatopoeia",
    "Multiword",
    "Syntax-Case-Clause",
    "Sense-Semantic Relation",
    "Usage-Context-Pragmatics",
    "Document Structure",
    "Evidence-Provenance-Rights",
]


class RouterLaneSkip(BaseModel):
    lane: JapaneseFunctionLane
    reason: str = Field(min_length=1)


class RouterRetrievalLimits(BaseModel):
    max_candidates_per_lane: int = Field(ge=1)
    max_total_candidates: int = Field(ge=1)
    max_recovery_passes: int = Field(ge=0)
    max_work_ms: float = Field(gt=0)


class RouterTrace(BaseModel):
    """Inspectable routing decision without granting meaning authority."""

    detected_input_features: list[str] = Field(default_factory=list)
    router_decision: str = Field(min_length=1)
    candidate_lanes: list[JapaneseFunctionLane] = Field(default_factory=list)
    selected_lanes: list[JapaneseFunctionLane] = Field(default_factory=list)
    skipped_lanes: list[RouterLaneSkip] = Field(default_factory=list)
    secondary_facets: list[str] = Field(default_factory=list)
    fallback_reason: str | None = None
    recovery_needed: bool = False
    routing_version: str = Field(min_length=1)
    projection_version: str = Field(min_length=1)
    retrieval_limits: RouterRetrievalLimits

    @model_validator(mode="after")
    def validate_lane_accounting(self) -> "RouterTrace":
        candidates = set(self.candidate_lanes)
        selected = set(self.selected_lanes)
        skipped = {item.lane for item in self.skipped_lanes}
        if len(candidates) != len(self.candidate_lanes):
            raise ValueError("candidate_lanes must be unique")
        if len(selected) != len(self.selected_lanes):
            raise ValueError("selected_lanes must be unique")
        if not selected.issubset(candidates):
            raise ValueError("selected_lanes must be a subset of candidate_lanes")
        if selected & skipped:
            raise ValueError("selected_lanes cannot also be skipped")
        if self.recovery_needed and not self.fallback_reason:
            raise ValueError("recovery_needed requires fallback_reason")
        return self


RecoveryOperation = Literal[
    "kana_variant",
    "dakuten_handakuten",
    "small_kana",
    "long_vowel",
    "okurigana",
    "contraction",
    "insertion",
    "deletion",
    "substitution",
    "transposition",
    "split",
    "merge",
    "declared_alias",
]


class RecoveryCandidateEvidence(BaseModel):
    candidate_text: str = Field(min_length=1)
    runtime_record_ids: list[str] = Field(default_factory=list)
    operations: list[RecoveryOperation] = Field(default_factory=list)
    recovery_cost: float = Field(ge=0)
    score_components: dict[str, float] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_runtime_landing(self) -> "RecoveryCandidateEvidence":
        if not self.runtime_record_ids:
            raise ValueError("recovery candidate must land on runtime data")
        if not self.evidence_ids:
            raise ValueError("recovery candidate requires evidence_ids")
        return self


class RecoveryInterpretationEvidence(BaseModel):
    """Evidence contract for bounded recovery before MeaningGraph attachment."""

    recovery_version: str = Field(min_length=1)
    original_span: OriginalSpan
    original_text: str
    candidates: list[RecoveryCandidateEvidence] = Field(default_factory=list)
    selected_candidate: str | None = None
    absolute_score: float | None = None
    margin: float | None = None
    minimum_score: float = Field(ge=0)
    minimum_margin: float = Field(ge=0)
    decision: Literal["RESOLVED", "AMBIGUOUS", "INSUFFICIENT"]
    changed_action_semantics: bool = False
    protected_element_changed: bool = False
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_resolution_gate(self) -> "RecoveryInterpretationEvidence":
        candidate_texts = {item.candidate_text for item in self.candidates}
        if self.protected_element_changed:
            if self.decision == "RESOLVED":
                raise ValueError("protected-element change cannot resolve")
        if self.decision == "RESOLVED":
            if not self.selected_candidate:
                raise ValueError("resolved recovery requires selected_candidate")
            if self.selected_candidate not in candidate_texts:
                raise ValueError("selected_candidate must be present in candidates")
            if self.absolute_score is None or self.margin is None:
                raise ValueError("resolved recovery requires score and margin")
            if self.absolute_score < self.minimum_score:
                raise ValueError("resolved recovery is below minimum_score")
            if self.margin < self.minimum_margin:
                raise ValueError("resolved recovery is below minimum_margin")
            if not self.evidence_ids:
                raise ValueError("resolved recovery requires evidence_ids")
        elif self.selected_candidate is not None:
            raise ValueError("unresolved recovery must not select a candidate")
        return self

    @property
    def external_action_safe(self) -> bool:
        return (
            self.decision == "RESOLVED"
            and not self.changed_action_semantics
            and not self.protected_element_changed
        )


EvidenceAuthorityRole = Literal[
    "semantic_authority",
    "ranking_evidence",
    "provenance_only",
    "permission_only",
]


class FieldEvidenceReference(BaseModel):
    """Field-level provenance and rights; missing permission always fails closed."""

    evidence_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    field_semantics: str = Field(min_length=1)
    license_or_rights_lane: str = Field(min_length=1)
    authority_role: EvidenceAuthorityRole
    allowed_consumers: list[str] = Field(default_factory=list)
    allowed_uses: list[str] = Field(default_factory=list)
    forbidden_uses: list[str] = Field(default_factory=list)
    public_runtime_eligible: bool = False
    source_artifact_sha256: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_explicit_permission(self) -> "FieldEvidenceReference":
        if self.public_runtime_eligible:
            if not self.allowed_consumers:
                raise ValueError("runtime-eligible field requires allowed_consumers")
            if not self.allowed_uses:
                raise ValueError("runtime-eligible field requires allowed_uses")
        return self

    def permits(self, *, consumer: str, use: str) -> bool:
        return (
            self.public_runtime_eligible
            and consumer in self.allowed_consumers
            and use in self.allowed_uses
            and use not in self.forbidden_uses
        )
