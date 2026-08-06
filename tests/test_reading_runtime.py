import pytest

from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine


@pytest.fixture(scope="module")
def engine() -> ParserEngine:
    return ParserEngine()


def _analyze(engine: ParserEngine, text: str, *, external: bool = False):
    return engine.analyze(AnalyzeRequest(
        original_text=text,
        execution_mode="external_action" if external else "analysis",
    ))


def test_ordinary_sentence_becomes_non_executable_reading_structure(engine):
    response = _analyze(engine, "開発者が設定を変更した。", external=True)
    reading = response.meaning_graph.reading_analysis

    assert reading.purpose == "japanese_reading_comprehension"
    assert reading.status == "RESOLVED"
    assert len(reading.predicate_frames) == 1
    frame = reading.predicate_frames[0]
    assert frame.predicate == "変更する"
    assert frame.tense == "past"
    assert {(item.role, item.value) for item in frame.arguments} == {
        ("agent", "開発者"),
        ("object", "設定"),
    }
    assert response.meaning_graph.propositions[0].intent_type == "observation"
    assert not response.meaning_graph.propositions[0].executable_candidate
    assert not response.execution_allowed


def test_partial_negation_and_quantifier_keep_separate_scopes(engine):
    response = _analyze(engine, "すべての問題を解決できるわけではない。")
    reading = response.meaning_graph.reading_analysis
    operators = {
        (item.operator_type, item.semantic_value)
        for item in reading.scope_operators
    }

    assert ("negation", "partial_negation") in operators
    assert ("quantifier", "universal") in operators
    assert reading.predicate_frames[0].polarity == "negative"
    assert reading.predicate_frames[0].predicate == "出来る"


@pytest.mark.parametrize(
    ("text", "semantic_value"),
    [
        ("条件を満たせば、処理を実行する。", "general_condition"),
        ("テストが通ったら、公開する。", "event_condition"),
        ("雨なら、中止する。", "premise_condition"),
        ("このボタンを押すと、画面が切り替わる。", "natural_condition"),
        ("雨でも、実行する。", "concessive_condition"),
    ],
)
def test_condition_forms_are_not_collapsed(engine, text, semantic_value):
    response = _analyze(engine, text)
    assert any(
        item.operator_type == "condition"
        and item.semantic_value == semantic_value
        for item in response.meaning_graph.reading_analysis.scope_operators
    )


def test_quotation_preserves_source_and_hearsay(engine):
    response = _analyze(engine, "「削除しろ」と担当者が言ったらしい。")
    reading = response.meaning_graph.reading_analysis

    assert any(
        item.operator_type == "quotation"
        for item in reading.scope_operators
    )
    assert any(
        item.operator_type == "modality"
        and item.semantic_value == "hearsay"
        for item in reading.scope_operators
    )
    assert not any(
        item.operator_type == "condition"
        for item in reading.scope_operators
    )
    attribution = reading.attribution_frames[0]
    assert attribution.source == "担当者"
    assert attribution.reporting_predicate == "言った"
    assert attribution.status == "RESOLVED"


def test_discourse_relation_connects_adjacent_clauses(engine):
    response = _analyze(engine, "結果は改善した。しかし、例外は残った。")
    relation = response.meaning_graph.reading_analysis.discourse_relations[0]

    assert relation.relation == "contrasts_with"
    assert relation.marker == "しかし"
    assert relation.source_clause_id != relation.target_clause_id


def test_conditional_external_action_is_blocked_until_condition_is_evaluated(
    engine,
):
    response = _analyze(
        engine,
        "テストが通ったらAPIを公開しろ。",
        external=True,
    )

    assert not response.execution_allowed
    assert "CONDITIONAL_ACTION_REQUIRES_EVALUATION" in response.blocked_reasons


@pytest.mark.parametrize(
    "text",
    [
        "APIを確認していただけますか。",
        "この資料を共有してもらえませんか。",
        "このAPIを確認していただけないでしょうか。",
    ],
)
def test_polite_request_is_not_misread_as_question_negation_or_condition(
    engine,
    text,
):
    response = _analyze(engine, text, external=True)
    operator_types = {
        item.operator_type
        for item in response.meaning_graph.reading_analysis.scope_operators
    }

    assert response.execution_allowed
    assert "INTERROGATIVE_ACTION" not in response.blocked_reasons
    assert "negation" not in operator_types
    assert "condition" not in operator_types


def test_reading_analysis_is_deterministic(engine):
    request = AnalyzeRequest(original_text="結果は改善した。しかし、例外は残った。")
    first = engine.analyze(request)
    second = engine.analyze(request)

    assert first.meaning_graph.semantic_hash == second.meaning_graph.semantic_hash
    assert (
        first.meaning_graph.reading_analysis
        == second.meaning_graph.reading_analysis
    )
