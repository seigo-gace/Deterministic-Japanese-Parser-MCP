from dataclasses import replace

from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine
from deterministic_japanese_parser_mcp.config import SETTINGS
from deterministic_japanese_parser_mcp.normalizer import normalize_with_map


TEXT = "旧仕様ではなく新仕様を採用する。ただしUIは変更するな。"


def _engine() -> ParserEngine:
    return ParserEngine(settings=replace(SETTINGS, hard_deadline_ms=60_000))


def test_tadashi_exception_rule_is_detected_by_indexed_and_exhaustive_paths():
    engine = _engine()
    normalized, mapping = normalize_with_map(TEXT)

    indexed, indexed_timeouts = engine.rules.extract(
        normalized,
        mapping,
        TEXT,
    )
    exhaustive, exhaustive_timeouts = engine.rules.extract_exhaustive(
        normalized,
        mapping,
        TEXT,
    )

    assert not indexed_timeouts
    assert not exhaustive_timeouts
    assert "exception" in {item.type for item in indexed}
    assert "exception" in {item.type for item in exhaustive}


def test_tadashi_exception_survives_meaning_graph_and_legacy_view():
    response = _engine().analyze(
        AnalyzeRequest(original_text=TEXT, deadline_ms=60_000)
    )

    proposition_types = {
        item.intent_type for item in response.meaning_graph.propositions
    }
    legacy_types = {item.type for item in response.intents}

    assert "exception" in proposition_types
    assert "exception" in legacy_types
