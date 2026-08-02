from mcp.server.fastmcp import FastMCP
from .engine import ParserEngine
from .models import AnalyzeRequest, AnalyzeResponse

mcp=FastMCP("deterministic-japanese-parser")
_engine:ParserEngine|None=None
def engine()->ParserEngine:
    global _engine
    if _engine is None: _engine=ParserEngine()
    return _engine

@mcp.tool()
def analyze_japanese(request:AnalyzeRequest)->AnalyzeResponse:
    """Deterministically analyze Japanese text into intents, metaphors, references, and task packets."""
    return engine().analyze(request)

def analyze_sync(request:AnalyzeRequest)->AnalyzeResponse: return engine().analyze(request)
def main()->None: mcp.run(transport="stdio")
if __name__=="__main__": main()
