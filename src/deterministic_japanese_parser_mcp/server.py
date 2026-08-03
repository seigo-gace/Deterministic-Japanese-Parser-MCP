from mcp.server.fastmcp import FastMCP

from .engine import ParserEngine
from .models import AnalysisDepth, AnalyzeRequest, AnalyzeResponse, ExecutionMode

mcp = FastMCP("deterministic-japanese-parser", json_response=True)
_engine: ParserEngine | None = None


def engine() -> ParserEngine:
    global _engine
    if _engine is None:
        _engine = ParserEngine()
    return _engine


def prewarm() -> ParserEngine:
    """Load dictionaries, compile indexes, initialize Sudachi, and warm caches.

    This runs before the MCP stdio handshake so the first user tool call does
    not pay dependency loading or dictionary initialization costs.
    """
    instance = engine()
    response = instance.analyze(AnalyzeRequest(
        original_text="UIは残せ。APIだけ変更しろ。",
        deadline_ms=60000,
    ))
    if not response.intents:
        raise RuntimeError("parser prewarm validation produced no intents")
    return instance


@mcp.tool()
def analyze_japanese(
    original_text: str,
    conversation_context: list[str] | None = None,
    known_entities: list[str] | None = None,
    protected_elements: list[str] | None = None,
    execution_mode: ExecutionMode = ExecutionMode.ANALYSIS,
    analysis_depth: AnalysisDepth = AnalysisDepth.AUTO,
    deadline_ms: int = 2000,
) -> AnalyzeResponse:
    """Deterministically analyze Japanese text into intents, references, and Task Packets."""
    request = AnalyzeRequest(
        original_text=original_text,
        conversation_context=conversation_context or [],
        known_entities=known_entities or [],
        protected_elements=protected_elements or [],
        execution_mode=execution_mode,
        analysis_depth=analysis_depth,
        deadline_ms=deadline_ms,
    )
    return engine().analyze(request)


def analyze_sync(request: AnalyzeRequest) -> AnalyzeResponse:
    return engine().analyze(request)


def main() -> None:
    prewarm()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
