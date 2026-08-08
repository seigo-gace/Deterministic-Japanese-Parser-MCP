from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class AnalysisDepth(str, Enum):
    AUTO = "auto"
    FAST = "fast"
    DEEP = "deep"


class ExecutionMode(str, Enum):
    ANALYSIS = "analysis"
    COMPARISON = "comparison"
    PLANNING = "planning"
    EXTERNAL_ACTION = "external_action"


class OverallStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class ItemStatus(str, Enum):
    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    INSUFFICIENT = "INSUFFICIENT"
    CONTRADICTORY = "CONTRADICTORY"
    UNSUPPORTED = "UNSUPPORTED"
    TIMEOUT = "TIMEOUT"


class SocialParticipant(BaseModel):
    entity_id: str
    groups: list[str] = Field(default_factory=list)
    role: str | None = None
    relation_to_speaker: str | None = None
    relation_to_addressee: str | None = None


class SocialContext(BaseModel):
    speaker: SocialParticipant | None = None
    addressee: SocialParticipant | None = None
    mentioned_people: list[SocialParticipant] = Field(default_factory=list)
    setting: str | None = None
    formality: str | None = None
    speaker_group: str | None = None
    addressee_group: str | None = None


class AnalyzeRequest(BaseModel):
    original_text: str
    conversation_context: list[str] = Field(default_factory=list)
    known_entities: list[str] = Field(default_factory=list)
    protected_elements: list[str] = Field(default_factory=list)
    social_context: SocialContext = Field(default_factory=SocialContext)
    discourse_state: dict[str, Any] = Field(default_factory=dict)
    execution_mode: ExecutionMode = ExecutionMode.ANALYSIS
    analysis_depth: AnalysisDepth = AnalysisDepth.AUTO
    deadline_ms: int = Field(default=50, ge=1, le=60000)

    @field_validator("original_text")
    @classmethod
    def non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("original_text must not be empty")
        return value


class OriginalSpan(BaseModel):
    start: int
    end: int
    source_text: str


class LexicalCandidate(BaseModel):
    record_id: str
    lemma: str
    matched_text: str
    match_type: Literal["surface", "normalized", "reading"]
    readings: list[str] = Field(default_factory=list)
    restricted_to: list[str] = Field(default_factory=list)
    no_kanji: bool = False
    part_of_speech: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    usage_labels: list[str] = Field(default_factory=list)
    source_dataset: str | None = None
    source_version: str | None = None
    source_license: str | None = None


class Token(BaseModel):
    surface: str
    normalized: str
    reading: str | None = None
    pos: list[str]
    span: OriginalSpan
    lexical_candidates: list[LexicalCandidate] = Field(default_factory=list)
    lexical_candidate_total: int = 0
    lexical_status: Literal["MATCHED", "AMBIGUOUS", "NO_MATCH"] = "NO_MATCH"


class LexicalNode(BaseModel):
    lexical_node_id: str
    surface: str
    normalized: str
    reading: str | None = None
    pos: list[str] = Field(default_factory=list)
    source_span: OriginalSpan
    candidates: list[LexicalCandidate] = Field(default_factory=list)
    candidate_scores: dict[str, int] = Field(default_factory=dict)
    candidate_evidence: dict[str, list[str]] = Field(default_factory=dict)
    selected_record_id: str | None = None
    resolution_reason: str = "no_candidates"
    resolution_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    related_proposition_ids: list[str] = Field(default_factory=list)
    related_entity_ids: list[str] = Field(default_factory=list)
    related_sense_ids: list[str] = Field(default_factory=list)
    status: ItemStatus = ItemStatus.AMBIGUOUS


class Intent(BaseModel):
    type: str
    value: str
    captures: dict[str, str] = Field(default_factory=dict)
    rule_id: str | None = None
    priority: int = 0
    span: OriginalSpan
    status: ItemStatus = ItemStatus.RESOLVED


class Metaphor(BaseModel):
    expression: str
    interpretation: str
    domain: str
    context_matches: list[str] = Field(default_factory=list)
    span: OriginalSpan
    status: ItemStatus = ItemStatus.RESOLVED


class LanguageFeatureMatch(BaseModel):
    entry_id: str
    feature_type: str
    surface: str
    interpretation_id: str | None = None
    interpretation: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    register_profile: dict[str, Any] = Field(default_factory=dict)
    source_span: OriginalSpan
    status: ItemStatus = ItemStatus.RESOLVED
    candidate_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    risk_class: str = "semantic"


class ReferenceResolution(BaseModel):
    expression: str
    candidates: list[str] = Field(default_factory=list)
    selected: str | None = None
    candidate_scores: dict[str, int] = Field(default_factory=dict)
    resolution_reason: str | None = None
    span: OriginalSpan
    status: ItemStatus


class SenseCandidate(BaseModel):
    sense_id: str
    label: str
    score: int
    evidence: list[str] = Field(default_factory=list)


class Entity(BaseModel):
    entity_id: str
    canonical: str
    entity_type: str = "unknown"
    mentions: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    source_spans: list[OriginalSpan] = Field(default_factory=list)
    salience: int = 0
    status: ItemStatus = ItemStatus.RESOLVED


class Argument(BaseModel):
    role: str
    value: str
    entity_id: str | None = None
    case_marker: str | None = None
    explicit: bool = True
    span: OriginalSpan | None = None
    candidates: list[str] = Field(default_factory=list)
    status: ItemStatus = ItemStatus.RESOLVED


class Clause(BaseModel):
    clause_id: str
    text: str
    clause_type: str = "main"
    proposition_ids: list[str] = Field(default_factory=list)
    parent_clause_id: str | None = None
    relation: str | None = None
    discourse_markers: list[str] = Field(default_factory=list)
    topic_entity_ids: list[str] = Field(default_factory=list)
    focus_entity_ids: list[str] = Field(default_factory=list)
    source_span: OriginalSpan
    status: ItemStatus = ItemStatus.RESOLVED


class Proposition(BaseModel):
    proposition_id: str
    predicate: str
    surface_predicate: str | None = None
    intent_type: str
    value: str
    captures: dict[str, str] = Field(default_factory=dict)
    arguments: list[Argument] = Field(default_factory=list)
    polarity: Literal["positive", "negative"] = "positive"
    sentence_mood: Literal[
        "declarative", "interrogative", "imperative"
    ] = "declarative"
    speech_act: str = "assertion"
    pragmatic_markers: list[str] = Field(default_factory=list)
    deontic_force: Literal[
        "none", "permission", "obligation", "prohibition"
    ] = "none"
    epistemic_status: str = "asserted"
    force_level: int | None = Field(default=None, ge=1, le=5)
    directness: str | None = None
    politeness_level: int | None = Field(default=None, ge=0, le=5)
    honorific_classes: list[str] = Field(default_factory=list)
    social_relation_status: str | None = None
    interaction_functions: list[str] = Field(default_factory=list)
    information_territory: str | None = None
    register_labels: list[str] = Field(default_factory=list)
    sensory_features: dict[str, Any] = Field(default_factory=dict)
    tense: str | None = None
    aspect: list[str] = Field(default_factory=list)
    voice: list[str] = Field(default_factory=lambda: ["active"])
    speaker_entity_id: str | None = None
    quoted: bool = False
    quote_source: str | None = None
    executable_candidate: bool = False
    clause_id: str | None = None
    source_span: OriginalSpan
    status: ItemStatus = ItemStatus.RESOLVED
    evidence_ids: list[str] = Field(default_factory=list)
    sense_id: str | None = None
    sense_label: str | None = None
    sense_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    sense_candidates: list[SenseCandidate] = Field(default_factory=list)
    inference_sources: list[str] = Field(default_factory=list)


class ScopeEdge(BaseModel):
    edge_id: str
    source_id: str
    target_id: str
    relation: str
    marker: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    status: ItemStatus = ItemStatus.RESOLVED
    evidence_ids: list[str] = Field(default_factory=list)


class DependencyArc(BaseModel):
    arc_id: str
    clause_id: str
    dependent_token_index: int
    head_token_index: int
    relation: str
    marker: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    status: ItemStatus = ItemStatus.RESOLVED


class PredicateFrame(BaseModel):
    frame_id: str
    clause_id: str
    predicate: str
    surface_predicate: str
    predicate_token_index: int
    arguments: list[Argument] = Field(default_factory=list)
    polarity: Literal["positive", "negative"] = "positive"
    tense: str | None = None
    aspect: list[str] = Field(default_factory=list)
    voice: list[str] = Field(default_factory=lambda: ["active"])
    modality: list[str] = Field(default_factory=list)
    related_proposition_ids: list[str] = Field(default_factory=list)
    source_span: OriginalSpan
    status: ItemStatus = ItemStatus.RESOLVED


class ScopeOperator(BaseModel):
    operator_id: str
    clause_id: str
    operator_type: str
    semantic_value: str
    marker: str
    source_span: OriginalSpan
    operand_spans: list[OriginalSpan] = Field(default_factory=list)
    target_frame_ids: list[str] = Field(default_factory=list)
    status: ItemStatus = ItemStatus.RESOLVED


class DiscourseRelation(BaseModel):
    relation_id: str
    source_clause_id: str
    target_clause_id: str
    relation: str
    marker: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    status: ItemStatus = ItemStatus.RESOLVED


class AttributionFrame(BaseModel):
    attribution_id: str
    clause_id: str
    attribution_type: str
    content_span: OriginalSpan
    source: str | None = None
    source_span: OriginalSpan | None = None
    reporting_predicate: str | None = None
    related_frame_ids: list[str] = Field(default_factory=list)
    status: ItemStatus = ItemStatus.RESOLVED


class ReadingAnalysis(BaseModel):
    analysis_version: str = "1.0.0"
    purpose: Literal["japanese_reading_comprehension"] = (
        "japanese_reading_comprehension"
    )
    predicate_frames: list[PredicateFrame] = Field(default_factory=list)
    dependency_arcs: list[DependencyArc] = Field(default_factory=list)
    scope_operators: list[ScopeOperator] = Field(default_factory=list)
    attribution_frames: list[AttributionFrame] = Field(default_factory=list)
    discourse_relations: list[DiscourseRelation] = Field(default_factory=list)
    unresolved: list[dict[str, Any]] = Field(default_factory=list)
    status: ItemStatus = ItemStatus.RESOLVED


class DecisionStateChange(BaseModel):
    change_type: str
    proposition_id: str
    target: str | None = None
    previous_state: str | None = None
    new_state: str | None = None


class MeaningGraph(BaseModel):
    graph_version: str = "2.3.0"
    semantic_hash: str = ""
    entities: list[Entity] = Field(default_factory=list)
    clauses: list[Clause] = Field(default_factory=list)
    propositions: list[Proposition] = Field(default_factory=list)
    lexical_nodes: list[LexicalNode] = Field(default_factory=list)
    scope_edges: list[ScopeEdge] = Field(default_factory=list)
    reading_analysis: ReadingAnalysis = Field(default_factory=ReadingAnalysis)
    language_features: list[LanguageFeatureMatch] = Field(default_factory=list)
    unresolved: list[dict[str, Any]] = Field(default_factory=list)
    decision_state_changes: list[DecisionStateChange] = Field(
        default_factory=list
    )
    evidence_rule_ids: list[str] = Field(default_factory=list)
    context_version: str = ""
    quality_annotations: dict[str, Any] = Field(default_factory=dict)


class TaskConstraint(BaseModel):
    constraint_type: str
    value: str
    source_proposition_id: str | None = None
    source_span: OriginalSpan | None = None
    status: ItemStatus = ItemStatus.RESOLVED


class Task(BaseModel):
    task_id: str
    action: str
    target: str | None = None
    intent_type: str
    execution_order: int = 0
    constraints: list[str] = Field(default_factory=list)
    structured_constraints: list[TaskConstraint] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    completion_criteria: list[str] = Field(default_factory=list)
    verification_criteria: list[str] = Field(default_factory=list)
    external_action: bool = False
    status: ItemStatus = ItemStatus.RESOLVED
    original_span: OriginalSpan
    proposition_id: str | None = None


class TaskGraph(BaseModel):
    graph_version: str = "2.0.0"
    tasks: list[Task] = Field(default_factory=list)
    edges: list[dict[str, str]] = Field(default_factory=list)
    constraints: list[TaskConstraint] = Field(default_factory=list)
    status: ItemStatus = ItemStatus.RESOLVED


class AnalyzeResponse(BaseModel):
    overall_status: OverallStatus
    execution_allowed: bool
    blocked_reasons: list[str] = Field(default_factory=list)
    original_text: str
    normalized_text: str
    analysis_path: Literal["FAST", "DEEP", "FAILED"]
    tokens: list[Token] = Field(default_factory=list)
    meaning_graph: MeaningGraph = Field(default_factory=MeaningGraph)
    task_graph: TaskGraph = Field(default_factory=TaskGraph)
    intents: list[Intent] = Field(default_factory=list)
    metaphors: list[Metaphor] = Field(default_factory=list)
    references: list[ReferenceResolution] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)
    ambiguities: list[dict[str, Any]] = Field(default_factory=list)
    missing_information: list[dict[str, Any]] = Field(default_factory=list)
    contradictions: list[dict[str, Any]] = Field(default_factory=list)
    unsupported_elements: list[dict[str, Any]] = Field(default_factory=list)
    timeouts: list[dict[str, Any]] = Field(default_factory=list)
    versions: dict[str, str] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
