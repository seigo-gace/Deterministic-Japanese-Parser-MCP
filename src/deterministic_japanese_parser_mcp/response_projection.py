from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import models as _models

IncludeSection = Literal[
    "original_text",
    "normalized_text",
    "analysis_path",
    "tokens",
    "meaning_graph",
    "task_graph",
    "intents",
    "metaphors",
    "references",
    "tasks",
    "ambiguities",
    "missing_information",
    "contradictions",
    "unsupported_elements",
    "timeouts",
    "versions",
    "metrics",
]

INCLUDE_SECTIONS: tuple[str, ...] = (
    "original_text",
    "normalized_text",
    "analysis_path",
    "tokens",
    "meaning_graph",
    "task_graph",
    "intents",
    "metaphors",
    "references",
    "tasks",
    "ambiguities",
    "missing_information",
    "contradictions",
    "unsupported_elements",
    "timeouts",
    "versions",
    "metrics",
)


class AnalyzeRequest(_models.AnalyzeRequest):
    """Backward-compatible AnalyzeRequest with transport response projection.

    `include` does not alter semantic analysis.  It is consumed only by MCP/REST
    transport projection after the full AnalyzeResponse has been produced.
    """

    include: list[IncludeSection] | None = None


class AnalyzeToolResponse(BaseModel):
    """MCP/REST response contract supporting optional projected sections."""

    model_config = ConfigDict(extra="forbid")

    overall_status: _models.OverallStatus
    execution_allowed: bool
    blocked_reasons: list[str] = Field(default_factory=list)
    semantic_hash: str

    original_text: str | None = None
    normalized_text: str | None = None
    analysis_path: Literal["FAST", "DEEP", "FAILED"] | None = None
    tokens: list[_models.Token] | None = None
    meaning_graph: _models.MeaningGraph | None = None
    task_graph: _models.TaskGraph | None = None
    intents: list[_models.Intent] | None = None
    metaphors: list[_models.Metaphor] | None = None
    references: list[_models.ReferenceResolution] | None = None
    tasks: list[_models.Task] | None = None
    ambiguities: list[dict[str, Any]] | None = None
    missing_information: list[dict[str, Any]] | None = None
    contradictions: list[dict[str, Any]] | None = None
    unsupported_elements: list[dict[str, Any]] | None = None
    timeouts: list[dict[str, Any]] | None = None
    versions: dict[str, str] | None = None
    metrics: dict[str, Any] | None = None


def install_analyze_request_projection() -> None:
    """Expose the extended request as the package's authoritative model.

    The project already installs deterministic semantic refinements during
    package initialization.  This installer follows the same pattern while
    leaving the engine response model unchanged.
    """

    _models.AnalyzeRequest = AnalyzeRequest


def project_response(
    response: _models.AnalyzeResponse,
    include: list[IncludeSection] | None,
) -> dict[str, Any]:
    """Project an already-computed full response without changing semantics."""

    full = response.model_dump(mode="json")
    projected: dict[str, Any] = {
        "overall_status": full["overall_status"],
        "execution_allowed": full["execution_allowed"],
        "blocked_reasons": full["blocked_reasons"],
        "semantic_hash": full["meaning_graph"]["semantic_hash"],
    }

    names = INCLUDE_SECTIONS if include is None else tuple(dict.fromkeys(include))
    for name in names:
        projected[name] = full[name]

    # Validate the projected wire contract here so MCP and REST cannot diverge.
    return AnalyzeToolResponse.model_validate(projected).model_dump(
        mode="json",
        exclude_none=True,
    )
