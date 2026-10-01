import asyncio
import json

import pytest
from pydantic import ValidationError

from deterministic_japanese_parser_mcp import server
from deterministic_japanese_parser_mcp.mcp_output import (
    McpAnalyzeRequest,
    project_mcp_response,
)
from deterministic_japanese_parser_mcp.models import (
    AnalyzeRequest,
    AnalyzeResponse,
    OverallStatus,
)


class _Settings:
    hard_deadline_ms = 50
    target_latency_ms = 10


class _CountingEngine:
    def __init__(self) -> None:
        self.settings = _Settings()
        self.calls = 0
        self.requests: list[AnalyzeRequest] = []

    def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        self.calls += 1
        self.requests.append(request)
        return AnalyzeResponse(
            overall_status=OverallStatus.COMPLETE,
            execution_allowed=True,
            original_text=request.original_text,
            normalized_text=request.original_text,
            analysis_path="FAST",
            meaning_graph={"semantic_hash": "stable-semantic-hash"},
            metrics={
                "requested_deadline_ms": request.deadline_ms,
                "effective_deadline_ms": min(request.deadline_ms, 50),
                "total_ms": 1.0,
                "elapsed_ms": 1.0,
                "target_met": True,
                "hard_deadline_met": True,
            },
        )


def _call(arguments: dict):
    return asyncio.run(server.call_tool(server.TOOL_NAME, arguments))


def _full_response() -> AnalyzeResponse:
    return AnalyzeResponse(
        overall_status=OverallStatus.PARTIAL,
        execution_allowed=False,
        blocked_reasons=["semantic_ambiguity"],
        original_text="APIだけ変更して。UIは残す。",
        normalized_text="APIだけ変更して。UIは残す。",
        analysis_path="DEEP",
        ambiguities=[{"kind": "target"}],
        missing_information=[{"kind": "subject"}],
        unsupported_elements=[{"kind": "new_word"}],
        meaning_graph={
            "semantic_hash": "hash-123",
            "unresolved": [{"kind": "sense"}],
            "context_version": "ctx-1",
            "quality_annotations": {"quality": "reviewed"},
        },
        metrics={"total_ms": 7.0, "hard_deadline_met": True},
    )


def test_transport_request_defaults_compact_and_strips_profile_from_core():
    request = McpAnalyzeRequest(original_text="直せ。")
    assert request.output_profile == "compact"

    core = request.to_core_request()
    assert type(core) is AnalyzeRequest
    assert "output_profile" not in core.model_dump()
    assert core.model_dump() == AnalyzeRequest(original_text="直せ。").model_dump()


def test_invalid_profile_fails_validation():
    with pytest.raises(ValidationError):
        McpAnalyzeRequest.model_validate(
            {"original_text": "直せ。", "output_profile": "tiny"}
        )


def test_all_profiles_validate_against_existing_analyze_response_contract():
    source = _full_response()
    for profile in ("compact", "standard", "full"):
        projected = project_mcp_response(source, profile)
        validated = AnalyzeResponse.model_validate(projected)
        assert validated.meaning_graph.semantic_hash == "hash-123"


def test_compact_keeps_decision_ambiguity_and_semantic_identity():
    compact = project_mcp_response(_full_response(), "compact")

    assert compact["execution_allowed"] is False
    assert compact["blocked_reasons"] == ["semantic_ambiguity"]
    assert compact["ambiguities"] == [{"kind": "target"}]
    assert compact["meaning_graph"]["semantic_hash"] == "hash-123"
    assert "propositions" in compact["meaning_graph"]
    assert "tokens" not in compact
    assert "task_graph" not in compact
    assert "metrics" not in compact
    assert "lexical_nodes" not in compact["meaning_graph"]


def test_standard_keeps_task_and_reading_contract_but_drops_heavy_detail():
    standard = project_mcp_response(_full_response(), "standard")

    assert standard["meaning_graph"]["semantic_hash"] == "hash-123"
    assert "task_graph" in standard
    assert "reading_analysis" in standard["meaning_graph"]
    assert "predicate_frames" in standard["meaning_graph"]["reading_analysis"]
    assert "tokens" not in standard
    assert "lexical_nodes" not in standard["meaning_graph"]
    assert "paragraph_structure" not in standard["meaning_graph"]["reading_analysis"]
    assert "summary" not in standard["meaning_graph"]["reading_analysis"]
    assert "argumentation" not in standard["meaning_graph"]["reading_analysis"]


def test_tool_schema_adds_transport_profile_but_keeps_output_schema():
    tool = asyncio.run(server.list_tools())[0]

    assert "output_profile" in tool.inputSchema["properties"]
    assert tool.inputSchema["properties"]["output_profile"]["default"] == "compact"
    assert set(tool.inputSchema["properties"]["output_profile"]["enum"]) == {
        "compact",
        "standard",
        "full",
    }
    assert "output_profile" not in AnalyzeRequest.model_json_schema()["properties"]
    assert tool.outputSchema == AnalyzeResponse.model_json_schema()


def test_default_compact_projects_existing_structured_response(monkeypatch):
    instance = _CountingEngine()
    monkeypatch.setattr(server, "_engine", instance)
    server._response_cache.clear()

    result = _call({"original_text": "直せ。"})

    assert not result.isError
    assert result.structuredContent is not None
    assert "tokens" not in result.structuredContent
    assert "task_graph" not in result.structuredContent
    assert "metrics" not in result.structuredContent
    assert result.structuredContent["meaning_graph"]["semantic_hash"] == (
        "stable-semantic-hash"
    )
    assert instance.calls == 1


def test_explicit_full_preserves_existing_structured_response(monkeypatch):
    instance = _CountingEngine()
    monkeypatch.setattr(server, "_engine", instance)
    server._response_cache.clear()

    result = _call({"original_text": "直せ。", "output_profile": "full"})

    assert not result.isError
    assert result.structuredContent is not None
    assert "tokens" in result.structuredContent
    assert "task_graph" in result.structuredContent
    assert "metrics" in result.structuredContent
    assert result.structuredContent["meaning_graph"]["semantic_hash"] == (
        "stable-semantic-hash"
    )
    assert instance.calls == 1


def test_profile_switch_reuses_full_semantic_cache_and_preserves_summary(monkeypatch):
    instance = _CountingEngine()
    monkeypatch.setattr(server, "_engine", instance)
    server._response_cache.clear()

    compact = _call({"original_text": "直せ。", "output_profile": "compact"})
    standard = _call({"original_text": "直せ。", "output_profile": "standard"})
    full = _call({"original_text": "直せ。", "output_profile": "full"})

    assert instance.calls == 1
    assert all("output_profile" not in request.model_dump() for request in instance.requests)

    assert "tokens" not in compact.structuredContent
    assert "task_graph" not in compact.structuredContent
    assert "tokens" not in standard.structuredContent
    assert "task_graph" in standard.structuredContent
    assert "tokens" in full.structuredContent
    assert full.structuredContent["metrics"]["response_cache_hit"] == 1

    hashes = [
        result.structuredContent["meaning_graph"]["semantic_hash"]
        for result in (compact, standard, full)
    ]
    assert hashes == ["stable-semantic-hash"] * 3

    summaries = [
        json.loads(result.content[0].text)
        for result in (compact, standard, full)
    ]
    assert summaries[0] == summaries[1] == summaries[2]
