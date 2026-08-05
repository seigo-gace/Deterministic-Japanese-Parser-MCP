from __future__ import annotations

from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine


def test_checked_in_120k_lexicon_is_one_connected_runtime() -> None:
    engine = ParserEngine()
    runtime = engine.bundle.open_lexicon

    assert engine.bundle.lexicon["lookup_backend"] == "compiled-index"
    assert engine.bundle.lexicon["record_count"] == 120000
    assert runtime.available is True
    assert runtime.records_preloaded is True
    assert runtime.manifest["record_shards"] == 12
    assert len(runtime.record_locator) == 120000
    assert len(runtime._shard_cache) == 12
    assert sum(len(shard) for shard in runtime._shard_cache.values()) == 120000

    response = engine.analyze(
        AnalyzeRequest(original_text="日本を確認する。", deadline_ms=5000)
    )

    matched = [
        token
        for token in response.tokens
        if token.lexical_candidate_total > 0
    ]
    assert matched
    assert response.meaning_graph.lexical_nodes
    assert any(token.surface == "日本" for token in matched)
