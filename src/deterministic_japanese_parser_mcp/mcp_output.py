from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from .models import AnalyzeRequest, AnalyzeResponse

OutputProfile = Literal["compact", "standard", "full"]


class McpAnalyzeRequest(AnalyzeRequest):
    """MCP transport request layered on top of the semantic core request.

    ``output_profile`` is transport-only. ``to_core_request`` removes it before
    ParserEngine, semantic hashing, or response-cache identity can observe it.
    """

    output_profile: OutputProfile = Field(
        default="compact",
        description=(
            "Transport-only response profile. 'compact' is the default lightweight "
            "decision projection; 'standard' exposes additional semantic/task "
            "detail; 'full' preserves the complete AnalyzeResponse."
        ),
    )

    def to_core_request(self) -> AnalyzeRequest:
        return AnalyzeRequest.model_validate(
            self.model_dump(mode="python", exclude={"output_profile"})
        )


def _full_dict(response: AnalyzeResponse | dict[str, Any]) -> dict[str, Any]:
    if isinstance(response, AnalyzeResponse):
        return response.model_dump(mode="json")
    return response


def _selected(source: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: source[key] for key in keys if key in source}


def _compact_meaning_graph(graph: dict[str, Any]) -> dict[str, Any]:
    return _selected(
        graph,
        (
            "graph_version",
            "semantic_hash",
            "propositions",
            "unresolved",
            "context_version",
        ),
    )


def _standard_reading_analysis(reading: dict[str, Any]) -> dict[str, Any]:
    return _selected(
        reading,
        (
            "analysis_version",
            "purpose",
            "predicate_frames",
            "dependency_arcs",
            "scope_operators",
            "attribution_frames",
            "discourse_relations",
            "unresolved",
            "status",
        ),
    )


def _standard_meaning_graph(graph: dict[str, Any]) -> dict[str, Any]:
    projected = _selected(
        graph,
        (
            "graph_version",
            "semantic_hash",
            "entities",
            "clauses",
            "propositions",
            "scope_edges",
            "reading_analysis",
            "language_features",
            "unresolved",
            "decision_state_changes",
            "evidence_rule_ids",
            "context_version",
            "quality_annotations",
        ),
    )
    reading = graph.get("reading_analysis")
    if isinstance(reading, dict):
        projected["reading_analysis"] = _standard_reading_analysis(reading)
    return projected


def project_mcp_response(
    response: AnalyzeResponse | dict[str, Any],
    profile: OutputProfile,
) -> dict[str, Any]:
    """Project one full semantic result into an MCP transport profile.

    Projection is read-only: it does not change parser semantics, cache
    identity, or semantic_hash. Every profile retains AnalyzeResponse's
    required top-level fields so the existing output schema remains valid.
    """

    full = _full_dict(response)
    if profile == "full":
        return full

    if profile == "compact":
        compact = _selected(
            full,
            (
                "overall_status",
                "execution_allowed",
                "blocked_reasons",
                "original_text",
                "normalized_text",
                "analysis_path",
                "intents",
                "ambiguities",
                "missing_information",
                "contradictions",
                "unsupported_elements",
                "timeouts",
                "versions",
            ),
        )
        graph = full.get("meaning_graph")
        if isinstance(graph, dict):
            compact["meaning_graph"] = _compact_meaning_graph(graph)
        return compact

    if profile == "standard":
        standard = _selected(
            full,
            (
                "overall_status",
                "execution_allowed",
                "blocked_reasons",
                "original_text",
                "normalized_text",
                "analysis_path",
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
            ),
        )
        graph = full.get("meaning_graph")
        if isinstance(graph, dict):
            standard["meaning_graph"] = _standard_meaning_graph(graph)
        return standard

    raise ValueError(f"unsupported MCP output profile: {profile!r}")