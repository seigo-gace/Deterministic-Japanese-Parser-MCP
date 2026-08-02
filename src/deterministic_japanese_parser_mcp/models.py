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
    deadline_ms: int = Field(default=2000, ge=50, le=60000)

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


class Task(BaseModel):
    task_id: str
    action: str
    target: str | None = None
    intent_type: str
    execution_order: int = 0
    constraints: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    completion_criteria: list[str] = Field(default_factory=list)
    verification_criteria: list[str] = Field(default_factory=list)
    external_action: bool = False
    status: ItemStatus = ItemStatus.RESOLVED
    original_span: OriginalSpan


class AnalyzeResponse(BaseModel):
    overall_status: OverallStatus
    execution_allowed: bool
    blocked_reasons: list[str] = Field(default_factory=list)
    original_text: str
    normalized_text: str
    analysis_path: Literal["FAST", "DEEP", "FAILED"]
    tokens: list[Token] = Field(default_factory=list)
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
