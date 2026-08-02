import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent


ROOT = Path(__file__).resolve().parents[1]


async def _run_stdio_round_trip() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "deterministic_japanese_parser_mcp.server"],
        cwd=ROOT,
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            assert "analyze_japanese" in {tool.name for tool in tools.tools}

            result = await session.call_tool(
                "analyze_japanese",
                arguments={
                    "original_text": "UIは残せ。APIだけ変更しろ。",
                    "execution_mode": "external_action",
                },
            )
            assert not result.isError

            structured = getattr(result, "structuredContent", None)
            if structured is None:
                structured = getattr(result, "structured_content", None)

            if structured is None:
                text_blocks = [item.text for item in result.content if isinstance(item, TextContent)]
                assert text_blocks
                structured = json.loads(text_blocks[0])

            assert structured["original_text"] == "UIは残せ。APIだけ変更しろ。"
            intent_types = {item["type"] for item in structured["intents"]}
            assert {"preserve", "modify"} <= intent_types
            assert structured["overall_status"] in {"COMPLETE", "PARTIAL"}


def test_mcp_stdio_round_trip() -> None:
    asyncio.run(_run_stdio_round_trip())
