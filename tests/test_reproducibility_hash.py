from dataclasses import replace

from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine
from deterministic_japanese_parser_mcp.reproducibility import semantic_hash_v2


TEXT = "UIは維持する。APIだけ変更しろ。"


def test_semantic_hash_v1_and_v2_are_stable_for_same_runtime():
    engine = ParserEngine()
    first = engine.analyze(AnalyzeRequest(original_text=TEXT))
    second = engine.analyze(AnalyzeRequest(original_text=TEXT))

    assert first.meaning_graph.semantic_hash == second.meaning_graph.semantic_hash
    assert first.versions["semantic_hash_v1"] == first.meaning_graph.semantic_hash
    assert second.versions["semantic_hash_v1"] == second.meaning_graph.semantic_hash
    assert first.versions["semantic_hash_v2"] == second.versions["semantic_hash_v2"]
    assert first.versions["semantic_hash_v2_algorithm"] == "sha256-semantic-runtime-v2"


def test_runtime_version_change_changes_v2_without_changing_v1():
    engine = ParserEngine()
    response = engine.analyze(AnalyzeRequest(original_text=TEXT))
    snapshot = dict(engine.reproducibility_snapshot)
    changed = dict(snapshot)
    changed["engine_versions_sha256"] = "f" * 64

    changed_v2 = semantic_hash_v2(
        normalized_text=response.normalized_text,
        semantic_hash_v1=response.meaning_graph.semantic_hash,
        runtime_snapshot=changed,
    )

    assert response.versions["semantic_hash_v1"] == response.meaning_graph.semantic_hash
    assert changed_v2 != response.versions["semantic_hash_v2"]


def test_dictionary_snapshot_change_changes_v2():
    engine = ParserEngine()
    response = engine.analyze(AnalyzeRequest(original_text=TEXT))
    changed = dict(engine.reproducibility_snapshot)
    changed["dictionary_snapshot_sha256"] = "1" * 64

    assert semantic_hash_v2(
        normalized_text=response.normalized_text,
        semantic_hash_v1=response.meaning_graph.semantic_hash,
        runtime_snapshot=changed,
    ) != response.versions["semantic_hash_v2"]


def test_semantic_runtime_change_changes_v2():
    engine = ParserEngine()
    response = engine.analyze(AnalyzeRequest(original_text=TEXT))
    changed = dict(engine.reproducibility_snapshot)
    changed["semantic_runtime_sha256"] = "2" * 64

    assert semantic_hash_v2(
        normalized_text=response.normalized_text,
        semantic_hash_v1=response.meaning_graph.semantic_hash,
        runtime_snapshot=changed,
    ) != response.versions["semantic_hash_v2"]


def test_language_feature_asset_change_changes_v2():
    engine = ParserEngine()
    response = engine.analyze(AnalyzeRequest(original_text=TEXT))
    changed = dict(engine.reproducibility_snapshot)
    changed["language_feature_asset_sha256"] = "3" * 64

    assert semantic_hash_v2(
        normalized_text=response.normalized_text,
        semantic_hash_v1=response.meaning_graph.semantic_hash,
        runtime_snapshot=changed,
    ) != response.versions["semantic_hash_v2"]


def test_language_feature_asset_is_reported_even_without_feature_match():
    engine = ParserEngine()
    response = engine.analyze(AnalyzeRequest(original_text="単純な観測文です。"))

    assert "language_feature_asset" in response.versions
    assert response.versions["language_feature_asset"] == engine.reproducibility_snapshot[
        "language_feature_asset_sha256"
    ]
