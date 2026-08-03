import hashlib
import json
from time import perf_counter

from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine
from deterministic_japanese_parser_mcp.metaphor import MetaphorMatcher
from deterministic_japanese_parser_mcp.models import ExecutionMode, ItemStatus
from deterministic_japanese_parser_mcp.normalizer import (
    normalize_with_map,
    span_to_original,
)


def semantic_hash(response) -> str:
    value = response.model_dump(mode="json")
    value.pop("metrics", None)
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def serialized_intents(intents) -> list[dict]:
    return [intent.model_dump(mode="json") for intent in intents]


def test_grapheme_normalization_and_original_span():
    for original, expected in [("ば", "ば"), ("ｶﾞ", "ガ"), ("Å", "Å")]:
        normalized, mapping = normalize_with_map(original)
        assert normalized == expected
        assert (
            span_to_original(0, len(normalized), mapping, original).source_text
            == original
        )


def test_protected_code_is_not_normalized():
    normalized, _ = normalize_with_map("`ｶﾞ` 外はｶﾞ")
    assert normalized == "`ｶﾞ` 外はガ"


def test_reference_intent_and_resolver_share_the_same_span():
    engine = ParserEngine()
    response = engine.analyze(AnalyzeRequest(
        original_text="直前の案を変更しろ。",
        conversation_context=["最初の案"],
        execution_mode=ExecutionMode.EXTERNAL_ACTION,
        deadline_ms=60000,
    ))
    assert len(response.references) == 1
    assert response.references[0].expression == "直前の案"
    assert response.references[0].selected == "最初の案"
    assert response.references[0].span.source_text == "直前の案"
    assert response.execution_allowed


def test_unresolved_reference_blocks_external_action():
    engine = ParserEngine()
    response = engine.analyze(AnalyzeRequest(
        original_text="以前の構成を変更しろ。",
        execution_mode=ExecutionMode.EXTERNAL_ACTION,
        deadline_ms=60000,
    ))
    assert response.references[0].status == ItemStatus.INSUFFICIENT
    assert not response.execution_allowed
    assert (
        "AMBIGUOUS_OR_INSUFFICIENT_REFERENCE"
        in response.blocked_reasons
    )


def test_synonym_canonicalization_detects_conflict():
    engine = ParserEngine()
    response = engine.analyze(AnalyzeRequest(
        original_text="実装を維持しろ。開発を削除しろ。",
        execution_mode=ExecutionMode.EXTERNAL_ACTION,
        deadline_ms=60000,
    ))
    assert any(
        item["type"] == "preserve_change_conflict"
        for item in response.contradictions
    )
    assert not response.execution_allowed


def test_metaphor_required_context_uses_local_clause():
    matcher = MetaphorMatcher({"entries": [{
        "expression": "赤い旗",
        "interpretation": "危険兆候",
        "domain": "risk",
        "context": ["危険"],
        "context_policy": "required_any",
    }]})
    text = "危険について説明する。別件では赤い旗を確認した。"
    normalized, mapping = normalize_with_map(text)
    result = matcher.find(normalized, mapping, text)
    assert result[0].status == ItemStatus.AMBIGUOUS


def test_indexed_and_exhaustive_rules_are_semantically_identical():
    engine = ParserEngine()
    samples = [
        AnalyzeRequest(
            original_text="今のUIは殺すな。APIだけ変更しろ。",
            deadline_ms=60000,
        ),
        AnalyzeRequest(
            original_text="これを前の案と比較しろ。",
            conversation_context=["案A", "案B"],
            deadline_ms=60000,
        ),
        AnalyzeRequest(
            original_text="障害の火消しをして、落ち着いてから穴を全部塞げ。最後にGitHubへ入れろ。",
            deadline_ms=60000,
        ),
        AnalyzeRequest(
            original_text="ｶﾞを変更しろ。",
            deadline_ms=60000,
        ),
    ]
    for request in samples:
        indexed = engine.analyze(request).model_dump(mode="json")
        exhaustive = engine.analyze(
            request,
            exhaustive_rules=True,
        ).model_dump(mode="json")
        indexed.pop("metrics", None)
        exhaustive.pop("metrics", None)
        assert indexed == exhaustive


def test_indexed_and_exhaustive_intents_match_on_adversarial_unmatched_text():
    engine = ParserEngine()
    original = "あ" * 500
    normalized, mapping = normalize_with_map(original)
    indexed, _ = engine.rules.extract(
        normalized,
        mapping,
        original,
        deadline_at=perf_counter() + 60,
    )
    exhaustive, _ = engine.rules.extract_exhaustive(
        normalized,
        mapping,
        original,
        deadline_at=perf_counter() + 60,
    )
    assert serialized_intents(indexed) == serialized_intents(exhaustive)


def test_task_graph_adds_sequence_dependency():
    engine = ParserEngine()
    response = engine.analyze(AnalyzeRequest(
        original_text="まず調査しろ。次に修正しろ。",
        deadline_ms=60000,
    ))
    assert len(response.tasks) >= 2
    assert response.tasks[1].dependencies == [response.tasks[0].task_id]


def test_response_is_deterministic_for_100_runs():
    engine = ParserEngine()
    request = AnalyzeRequest(
        original_text="今のUIは殺すな。APIだけ変更しろ。",
        deadline_ms=60000,
    )
    assert len({semantic_hash(engine.analyze(request)) for _ in range(100)}) == 1


def test_total_metric_includes_all_recorded_phases():
    engine = ParserEngine()
    response = engine.analyze(AnalyzeRequest(
        original_text="APIだけ変更しろ。",
        deadline_ms=60000,
    ))
    assert response.metrics["total_ms"] >= response.metrics["tokenization_ms"]
    assert response.metrics["elapsed_ms"] == response.metrics["total_ms"]
