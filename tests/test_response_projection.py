import asyncio
import json

import pytest
from pydantic import ValidationError
from starlette.testclient import TestClient

from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine
from deterministic_japanese_parser_mcp.http_server import create_app
from deterministic_japanese_parser_mcp.response_projection import project_response
from deterministic_japanese_parser_mcp import server as server_module


TEXT = "UIは維持する。APIだけ変更しろ。"
CORE_KEYS = {
    "overall_status",
    "execution_allowed",
    "blocked_reasons",
    "semantic_hash",
}


def _client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DJPMCP_HTTP_API_KEY", "test-secret")
    monkeypatch.setenv("DJPMCP_HTTP_ALLOWED_HOSTS", "testserver")
    monkeypatch.delenv("DJPMCP_HTTP_ALLOW_UNAUTHENTICATED", raising=False)
    return TestClient(create_app())


def _semantic_hash(response) -> str:
    return response.meaning_graph.semantic_hash


def test_include_none_keeps_full_wire_response():
    engine = ParserEngine()
    response = engine.analyze(AnalyzeRequest(original_text=TEXT))
    projected = project_response(response, None)

    assert CORE_KEYS <= projected.keys()
    for key in (
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
    ):
        assert key in projected


def test_include_meaning_graph_returns_only_requested_section_plus_core():
    engine = ParserEngine()
    response = engine.analyze(AnalyzeRequest(original_text=TEXT))
    projected = project_response(response, ["meaning_graph"])

    assert set(projected) == CORE_KEYS | {"meaning_graph"}
    assert projected["semantic_hash"] == projected["meaning_graph"]["semantic_hash"]
    assert "task_graph" not in projected
    assert "tokens" not in projected


def test_invalid_include_is_rejected_by_request_schema():
    with pytest.raises(ValidationError):
        AnalyzeRequest.model_validate({
            "original_text": TEXT,
            "include": ["not_a_real_section"],
        })


def test_include_does_not_change_semantic_result():
    engine = ParserEngine()
    full = engine.analyze(AnalyzeRequest(original_text=TEXT))
    projected_request = engine.analyze(
        AnalyzeRequest(original_text=TEXT, include=["meaning_graph"])
    )

    assert _semantic_hash(full) == _semantic_hash(projected_request)
    assert full.meaning_graph == projected_request.meaning_graph
    assert full.task_graph == projected_request.task_graph
    assert full.overall_status == projected_request.overall_status
    assert full.execution_allowed == projected_request.execution_allowed
    assert full.blocked_reasons == projected_request.blocked_reasons


def test_include_is_excluded_from_semantic_cache_key():
    instance = ParserEngine()
    full = AnalyzeRequest(original_text=TEXT)
    graph_only = AnalyzeRequest(original_text=TEXT, include=["meaning_graph"])
    task_only = AnalyzeRequest(original_text=TEXT, include=["task_graph"])

    assert server_module._response_cache_key(full, instance) == server_module._response_cache_key(
        graph_only, instance
    )
    assert server_module._response_cache_key(full, instance) == server_module._response_cache_key(
        task_only, instance
    )


def test_mcp_projection_reuses_full_analysis_cache(monkeypatch: pytest.MonkeyPatch):
    instance = ParserEngine()
    server_module._engine = instance
    server_module._response_cache.clear()

    first = asyncio.run(server_module.call_tool(
        server_module.TOOL_NAME,
        {"original_text": TEXT, "include": ["meaning_graph"]},
    ))
    second = asyncio.run(server_module.call_tool(
        server_module.TOOL_NAME,
        {"original_text": TEXT, "include": ["task_graph"]},
    ))

    assert first.isError is False
    assert second.isError is False
    assert set(first.structuredContent) == CORE_KEYS | {"meaning_graph"}
    assert set(second.structuredContent) == CORE_KEYS | {"task_graph"}
    assert first.structuredContent["semantic_hash"] == second.structuredContent["semantic_hash"]
    assert len(server_module._response_cache) == 1

    server_module._engine = None
    server_module._response_cache.clear()


def test_rest_projection_and_validation(monkeypatch: pytest.MonkeyPatch):
    headers = {"Authorization": "Bearer test-secret"}
    with _client(monkeypatch) as client:
        projected = client.post(
            "/v1/analyze",
            headers=headers,
            json={"original_text": TEXT, "include": ["meaning_graph"]},
        )
        invalid = client.post(
            "/v1/analyze",
            headers=headers,
            json={"original_text": TEXT, "include": ["not_a_real_section"]},
        )

    assert projected.status_code == 200
    assert set(projected.json()) == CORE_KEYS | {"meaning_graph"}
    assert invalid.status_code == 422
    assert invalid.json()["error"] == "validation_error"


def test_decision_core_projection_reduces_serialized_size_by_at_least_half():
    engine = ParserEngine()
    response = engine.analyze(AnalyzeRequest(original_text=TEXT))
    full = project_response(response, None)
    core = project_response(response, [])

    full_bytes = len(json.dumps(full, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    core_bytes = len(json.dumps(core, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    reduction = 1 - (core_bytes / full_bytes)

    assert reduction >= 0.50, (full_bytes, core_bytes, reduction)
