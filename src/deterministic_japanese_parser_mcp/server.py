from __future__ import annotations

import asyncio
from collections import OrderedDict
import json
from time import perf_counter
from typing import Any

import mcp.server.stdio as mcp_stdio
import mcp.types as types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from pydantic import ValidationError

from .engine import ParserEngine
from .models import (
    AnalysisDepth,
    AnalyzeRequest,
    AnalyzeResponse,
    ExecutionMode,
    OverallStatus,
)
from .normalizer import normalize_with_map

SERVER_NAME = "deterministic-japanese-parser"
SERVER_VERSION = "0.4.0"
TOOL_NAME = "analyze_japanese"

server = Server(SERVER_NAME)
mcp = server
_engine: ParserEngine | None = None
_RESPONSE_CACHE_MAX_ENTRIES = 128
_response_cache: OrderedDict[tuple[object, str], dict[str, Any]] = OrderedDict()


def engine() -> ParserEngine:
    global _engine
    if _engine is None:
        _engine = ParserEngine()
    return _engine


def _response_cache_key(
    request: AnalyzeRequest,
    instance: ParserEngine,
) -> tuple[object, str]:
    """Bind a cached response to every semantic input and the engine snapshot.

    Requested deadlines at or above the configured hard limit are semantically
    equivalent because ParserEngine clamps them to that limit. The original
    requested value remains request-specific diagnostic data and is refreshed
    on a cache hit.
    """
    payload = request.model_dump(mode="json")
    payload["deadline_ms"] = min(
        request.deadline_ms,
        instance.settings.hard_deadline_ms,
    )
    return (
        instance,
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
    )


def _get_cached_response(
    request: AnalyzeRequest,
    instance: ParserEngine,
) -> dict[str, Any] | None:
    key = _response_cache_key(request, instance)
    cached = _response_cache.get(key)
    if cached is not None:
        _response_cache.move_to_end(key)
    return cached


def _store_cached_response(
    request: AnalyzeRequest,
    instance: ParserEngine,
    response: AnalyzeResponse,
    structured: dict[str, Any] | None = None,
) -> None:
    if (
        response.overall_status != OverallStatus.COMPLETE
        or not response.metrics.get("hard_deadline_met")
    ):
        return
    key = _response_cache_key(request, instance)
    if structured is None:
        structured = response.model_dump(mode="json")
    _response_cache[key] = structured
    _response_cache.move_to_end(key)
    while len(_response_cache) > _RESPONSE_CACHE_MAX_ENTRIES:
        _response_cache.popitem(last=False)


def _cache_hit_response(
    structured: dict[str, Any],
    request: AnalyzeRequest,
    instance: ParserEngine,
    started: float,
) -> dict[str, Any]:
    elapsed_ms = round((perf_counter() - started) * 1000, 3)
    metrics = {
        **{
            key: (0.0 if key.endswith("_ms") else value)
            for key, value in structured.get("metrics", {}).items()
        },
        "requested_deadline_ms": request.deadline_ms,
        "effective_deadline_ms": min(
            request.deadline_ms,
            instance.settings.hard_deadline_ms,
        ),
        "response_cache_hit": 1,
        "total_ms": elapsed_ms,
        "elapsed_ms": elapsed_ms,
        "target_met": elapsed_ms <= instance.settings.target_latency_ms,
        "hard_deadline_met": elapsed_ms <= instance.settings.hard_deadline_ms,
    }
    return {**structured, "metrics": metrics}


def analyze_japanese(
    original_text: str,
    conversation_context: list[str] | None = None,
    known_entities: list[str] | None = None,
    protected_elements: list[str] | None = None,
    execution_mode: ExecutionMode = ExecutionMode.ANALYSIS,
    analysis_depth: AnalysisDepth = AnalysisDepth.AUTO,
    deadline_ms: int = 50,
) -> AnalyzeResponse:
    """Backwards-compatible direct Python entrypoint for the MCP tool."""
    return engine().analyze(AnalyzeRequest(
        original_text=original_text,
        conversation_context=conversation_context or [],
        known_entities=known_entities or [],
        protected_elements=protected_elements or [],
        execution_mode=execution_mode,
        analysis_depth=analysis_depth,
        deadline_ms=deadline_ms,
    ))


def prewarm() -> ParserEngine:
    """Complete cold initialization before the runtime deadline starts."""
    instance = engine()
    sample = "UIは残せ。APIだけ変更しろ。"

    # Sudachi performs lazy initialization on its first tokenization. That work
    # belongs to readiness, not to the 50 ms serving contract. Warm every lazy
    # component explicitly before validating the first deadline-bound response.
    normalized, mapping = normalize_with_map(sample)
    instance.tokenizer.tokenize(normalized, mapping, sample)
    instance.rules.candidate_indices(normalized)
    instance.metaphors.literal_matcher.matched_literals(normalized)
    AnalyzeRequest.model_json_schema()
    AnalyzeResponse.model_json_schema()

    request = AnalyzeRequest(
        original_text=sample,
        execution_mode=ExecutionMode.EXTERNAL_ACTION,
        deadline_ms=instance.settings.hard_deadline_ms,
    )
    response = instance.analyze(request)
    if not response.meaning_graph.propositions:
        raise RuntimeError("parser prewarm produced no MeaningGraph")
    if not response.task_graph.tasks:
        raise RuntimeError("parser prewarm produced no action TaskGraph")
    if not response.metrics.get("hard_deadline_met"):
        raise RuntimeError("parser prewarm exceeded the runtime hard deadline")
    _store_cached_response(request, instance, response)
    return instance


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name=TOOL_NAME,
            description=(
                "Deterministically read Japanese text and return lexical meaning, "
                "predicate-argument structure, negation/condition/modality scope, "
                "quotation attribution, discourse relations, a MeaningGraph, and "
                "downstream TaskGraph and external-action safety decisions."
            ),
            inputSchema=AnalyzeRequest.model_json_schema(),
            outputSchema=AnalyzeResponse.model_json_schema(),
        )
    ]


@server.call_tool(validate_input=False)
async def call_tool(
    name: str,
    arguments: dict[str, Any],
) -> types.CallToolResult:
    if name != TOOL_NAME:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"Unknown tool: {name}")],
            isError=True,
        )
    try:
        request = AnalyzeRequest.model_validate(arguments)
    except ValidationError as error:
        return types.CallToolResult(
            content=[types.TextContent(
                type="text",
                text=f"Input validation error: {error.errors(include_url=False)}",
            )],
            isError=True,
        )

    instance = engine()
    cache_started = perf_counter()
    structured = _get_cached_response(request, instance)
    if structured is None:
        response = instance.analyze(request)
        response = response.model_copy(update={
            "metrics": {
                **response.metrics,
                "response_cache_hit": 0,
            },
        })
        structured = response.model_dump(mode="json")
        _store_cached_response(request, instance, response, structured)
    else:
        structured = _cache_hit_response(
            structured,
            request,
            instance,
            cache_started,
        )
    summary = {
        "overall_status": structured["overall_status"],
        "execution_allowed": structured["execution_allowed"],
        "proposition_count": len(structured["meaning_graph"]["propositions"]),
        "predicate_frame_count": len(
            structured["meaning_graph"]["reading_analysis"]["predicate_frames"]
        ),
        "scope_operator_count": len(
            structured["meaning_graph"]["reading_analysis"]["scope_operators"]
        ),
        "action_task_count": len(structured["task_graph"]["tasks"]),
        "semantic_hash": structured["meaning_graph"]["semantic_hash"],
    }
    return types.CallToolResult(
        content=[types.TextContent(
            type="text",
            text=json.dumps(summary, ensure_ascii=False, separators=(",", ":")),
        )],
        structuredContent=structured,
        isError=False,
    )


def analyze_sync(request: AnalyzeRequest) -> AnalyzeResponse:
    return engine().analyze(request)


async def run() -> None:
    prewarm()
    async with mcp_stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name=SERVER_NAME,
                server_version=SERVER_VERSION,
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
