import asyncio

from deterministic_japanese_parser_mcp.models import (
    AnalyzeRequest,
    AnalyzeResponse,
    OverallStatus,
)
from deterministic_japanese_parser_mcp import server


class _Settings:
    hard_deadline_ms = 50
    target_latency_ms = 10


class _CountingEngine:
    def __init__(self) -> None:
        self.settings = _Settings()
        self.calls = 0

    def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        self.calls += 1
        return AnalyzeResponse(
            overall_status=OverallStatus.COMPLETE,
            execution_allowed=True,
            original_text=request.original_text,
            normalized_text=request.original_text,
            analysis_path="FAST",
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


def test_response_cache_preserves_semantics_and_refreshes_metrics(monkeypatch):
    instance = _CountingEngine()
    monkeypatch.setattr(server, "_engine", instance)
    server._response_cache.clear()

    ready_arguments = {
        "original_text": "UIは残せ。APIだけ変更しろ。",
        "execution_mode": "external_action",
        "deadline_ms": 50,
    }
    miss = _call(ready_arguments)
    hit = _call({**ready_arguments, "deadline_ms": 60000})

    assert instance.calls == 1
    assert miss.structuredContent is not None
    assert hit.structuredContent is not None
    miss_semantic = dict(miss.structuredContent)
    hit_semantic = dict(hit.structuredContent)
    miss_metrics = miss_semantic.pop("metrics")
    hit_metrics = hit_semantic.pop("metrics")
    assert miss_semantic == hit_semantic
    assert miss_metrics["response_cache_hit"] == 0
    assert hit_metrics["response_cache_hit"] == 1
    assert hit_metrics["requested_deadline_ms"] == 60000
    assert hit_metrics["effective_deadline_ms"] == 50


def test_response_cache_key_includes_context_and_engine_generation(monkeypatch):
    first_engine = _CountingEngine()
    monkeypatch.setattr(server, "_engine", first_engine)
    server._response_cache.clear()

    base = {"original_text": "直せ。", "deadline_ms": 50}
    _call(base)
    _call({**base, "conversation_context": ["案A"]})
    _call({**base, "discourse_state": {"current_topic": "API"}})
    assert first_engine.calls == 3

    second_engine = _CountingEngine()
    monkeypatch.setattr(server, "_engine", second_engine)
    _call(base)
    assert second_engine.calls == 1


def test_partial_response_is_not_cached(monkeypatch):
    instance = _CountingEngine()

    def partial(request: AnalyzeRequest) -> AnalyzeResponse:
        instance.calls += 1
        return AnalyzeResponse(
            overall_status=OverallStatus.PARTIAL,
            execution_allowed=False,
            original_text=request.original_text,
            normalized_text=request.original_text,
            analysis_path="FAST",
            metrics={"hard_deadline_met": True},
        )

    instance.analyze = partial
    monkeypatch.setattr(server, "_engine", instance)
    server._response_cache.clear()

    _call({"original_text": "曖昧。"})
    _call({"original_text": "曖昧。"})
    assert instance.calls == 2
