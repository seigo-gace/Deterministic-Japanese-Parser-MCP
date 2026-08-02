import pytest

mcp_module = pytest.importorskip("mcp")

from deterministic_japanese_parser_mcp.server import analyze_japanese, mcp


def test_mcp_tool_direct_call_returns_typed_response():
    response = analyze_japanese("UIは残せ。APIだけ変更しろ。")
    assert response.original_text == "UIは残せ。APIだけ変更しろ。"
    assert {intent.type for intent in response.intents} >= {"preserve", "modify"}
    assert mcp.name == "deterministic-japanese-parser"
