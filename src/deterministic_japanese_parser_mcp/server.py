from __future__ import annotations

import asyncio
import json
from typing import Any

import mcp.server.stdio as mcp_stdio
import mcp.types as types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from pydantic import ValidationError

from .semantic_engine import ParserEngine
from .models import AnalysisDepth, AnalyzeRequest, AnalyzeResponse, ExecutionMode
from .normalizer import normalize_with_map

SERVER_NAME = "deterministic-japanese-parser"
SERVER_VERSION = "0.2.0"
TOOL_NAME = "analyze_japanese"

server = Server(SERVER_NAME)
mcp = server
_engine: ParserEngine | None = None


def engine() -> ParserEngine:
    global _engine
    if _engine is None:
        _engine = ParserEngine()
    return _engine


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

    response = analyze_japanese(
        original_text=sample,
        deadline_ms=50,
    )
    if not response.meaning_graph.propositions:
        raise RuntimeError("parser prewarm produced no MeaningGraph")
    if not response.task_graph.tasks:
        raise RuntimeError("parser prewarm produced no action TaskGraph")
    if not response.metrics.get("hard_deadline_met"):
        raise RuntimeError("parser prewarm exceeded the runtime hard deadline")
    return instance


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name=TOOL_NAME,
            description=(
                "Deterministically transform Japanese text into a MeaningGraph, "
                "typed scope relations, an action TaskGraph, legacy compatibility "
                "views, and an action-relevance safety decision."
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

    response = engine().analyze(request)
    structured = response.model_dump(mode="json")
    summary = {
        "overall_status": structured["overall_status"],
        "execution_allowed": structured["execution_allowed"],
        "proposition_count": len(structured["meaning_graph"]["propositions"]),
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
