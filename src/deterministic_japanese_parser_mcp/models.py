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


class AnalyzeRequest(BaseModel):
    original_text: str
    conversation_context: list[str] = Field(default_factory=list)
    known_entities: list[str] = Field(default_factory=list)
    protected_elements: list[str] = Field(default_factory=list)
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


class Token(BaseModel):
    surface: str
    normalized: str
    pos: list[str]
    span: OriginalSpan


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


class ReferenceResolution(BaseModel):
    expression: str
    candidates: list[str] = Field(default_factory=list)
    selected: str | None = None
    span: OriginalSpan
    status: ItemStatus


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
    topic_entity_ids: list[str] = Field(default_factory=list)
    focus_entity_ids: list[str] = Field(default_factory=list)
    source_span: OriginalSpan
    status: ItemStatus = ItemStatus.RESOLVED


class Proposition(BaseModel):
    proposition_id: str
    predicate: str
    intent_type: str
    value: str
    captures: dict[str, str] = Field(default_factory=dict)
    arguments: list[Argument] = Field(default_factory=list)
    polarity: Literal["positive", "negative"] = "positive"
    sentence_mood: Literal[
        "declarative", "interrogative", "imperative"
    ] = "declarative"
    speech_act: str = "assertion"
    deontic_force: Literal[
        "none", "permission", "obligation", "prohibition"
    ] = "none"
    epistemic_status: str = "asserted"
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


class ScopeEdge(BaseModel):
    edge_id: str
    source_id: str
    target_id: str
    relation: str
    status: ItemStatus = ItemStatus.RESOLVED
    evidence_ids: list[str] = Field(default_factory=list)


class DecisionStateChange(BaseModel):
    change_type: str
    proposition_id: str
    target: str | None = None
    previous_state: str | None = None
    new_state: str | None = None


class MeaningGraph(BaseModel):
    graph_version: str = "2.0.0"
    semantic_hash: str = ""
    entities: list[Entity] = Field(default_factory=list)
    clauses: list[Clause] = Field(default_factory=list)
    propositions: list[Proposition] = Field(default_factory=list)
    scope_edges: list[ScopeEdge] = Field(default_factory=list)
    unresolved: list[dict[str, Any]] = Field(default_factory=list)
    decision_state_changes: list[DecisionStateChange] = Field(
        default_factory=list
    )
    evidence_rule_ids: list[str] = Field(default_factory=list)
    context_version: str = ""


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
