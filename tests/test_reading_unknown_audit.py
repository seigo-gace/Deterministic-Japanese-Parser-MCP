import pytest

from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine


@pytest.fixture(scope="module")
def engine() -> ParserEngine:
    return ParserEngine()


def _analyze(
    engine: ParserEngine,
    text: str,
    *,
    context: list[str] | None = None,
):
    return engine.analyze(AnalyzeRequest(
        original_text=text,
        conversation_context=context or [],
    ))


def _predicates(response) -> set[str]:
    return {
        item.predicate
        for item in response.meaning_graph.propositions
    }


def _has_question_meta(response) -> bool:
    return any(
        item.intent_type == "question"
        or item.predicate in {"質問する", "実行可能性を質問する"}
        for item in response.meaning_graph.propositions
    )


def _condition_scopes(response) -> list[tuple[str, str]]:
    reading = response.meaning_graph.reading_analysis
    return [
        (item.operator_type, item.semantic_value)
        for item in reading.scope_operators
        if item.operator_type == "condition"
    ]


def test_completion_imperatives_without_condition_proposition(engine):
    response = _analyze(engine, "処理が完了したら終了してください。")
    predicates = _predicates(response)

    assert str(response.overall_status) == "OverallStatus.COMPLETE"
    assert "終了する" in predicates
    assert "条件とする" not in predicates
    assert "要求する" not in predicates
    assert _condition_scopes(response)


def test_completion_with_holding_phrase(engine):
    response = _analyze(engine, "必要な確認をもって完了とする。")
    completion = [
        item
        for item in response.meaning_graph.propositions
        if item.intent_type == "completion_criteria"
    ]

    assert completion
    assert completion[0].predicate == "完了条件とする"
    assert "条件とする" not in _predicates(response)


def test_completion_only_when_all_pass(engine):
    response = _analyze(engine, "全件が通った場合のみ完了です。")
    completion = [
        item
        for item in response.meaning_graph.propositions
        if item.intent_type == "completion_criteria"
    ]

    assert str(response.overall_status) == "OverallStatus.COMPLETE"
    assert completion
    assert not response.meaning_graph.unresolved


def test_negated_failure_completion_criterion(engine):
    response = _analyze(engine, "失敗がなければ完了でよい。")

    assert any(
        item.intent_type == "completion_criteria"
        for item in response.meaning_graph.propositions
    )
    assert _condition_scopes(response)


def test_conditional_empty_input_returns_result(engine):
    response = _analyze(engine, "もし入力が空なら、空の結果を返してください。")
    predicates = _predicates(response)

    assert "返す" in predicates
    assert "条件とする" not in predicates
    assert _condition_scopes(response)


def test_dual_length_branching(engine):
    response = _analyze(engine, "入力が長いときは要約し、短いときはそのまま返す。")
    predicates = _predicates(response)

    assert str(response.overall_status) != "OverallStatus.FAILED"
    assert "要約する" in predicates
    assert "返す" in predicates
    assert len(_condition_scopes(response)) >= 2


def test_retry_on_failure_imperative(engine):
    response = _analyze(engine, "失敗したら再試行してください。")

    assert "再試行する" in _predicates(response)
    assert "条件とする" not in _predicates(response)
    assert _condition_scopes(response)


def test_concessive_logging_retained(engine):
    response = _analyze(engine, "例外が起きた場合でも、ログは残す。")

    assert str(response.overall_status) != "OverallStatus.FAILED"
    assert "残す" in _predicates(response)
    assert any(
        item.semantic_value == "concessive_condition"
        for item in response.meaning_graph.reading_analysis.scope_operators
    )


def test_deadline_discretion_condition(engine):
    response = _analyze(engine, "期限内に終わる限り、方法は任せる。")

    assert "任せる" in _predicates(response)
    assert _condition_scopes(response)


def test_prohibition_negation_do_not_stop(engine):
    response = _analyze(engine, "途中で止めないでください。")
    reading = response.meaning_graph.reading_analysis

    assert "止める" in _predicates(response)
    assert any(item.operator_type == "negation" for item in reading.scope_operators)


def test_meta_completion_questions(engine):
    for text in (
        "これは完了ですか。",
        "条件を満たしていますか。",
    ):
        response = _analyze(engine, text)
        reading = response.meaning_graph.reading_analysis

        assert str(response.overall_status) != "OverallStatus.FAILED"
        assert not _has_question_meta(response)
        assert any(item.operator_type == "question" for item in reading.scope_operators)


def test_inference_question_is_complete(engine):
    response = _analyze(engine, "再試行は必要でしょうか。")
    reading = response.meaning_graph.reading_analysis

    assert str(response.overall_status) == "OverallStatus.COMPLETE"
    assert any(item.operator_type == "question" for item in reading.scope_operators)
    assert not response.meaning_graph.unresolved


def test_sore_resolves_to_context(engine):
    response = _analyze(
        engine,
        "それが終わったら次へ進んでください。",
        context=["検証"],
    )
    resolution = next(
        item for item in response.references if item.expression == "それ"
    )

    assert resolution.selected == "検証"
    assert str(response.overall_status) != "OverallStatus.FAILED"


def test_sore_in_premise_resolves_to_context(engine):
    response = _analyze(
        engine,
        "もしそれが違うなら、別の方法で直してください。",
        context=["案A"],
    )
    resolution = next(
        item for item in response.references if item.expression == "それ"
    )

    assert resolution.selected == "案A"
    assert "条件とする" not in _predicates(response)


def test_gratitude_with_incomplete_tail(engine):
    response = _analyze(engine, "ありがとうございます、ただしまだ終わりではありません。")

    assert str(response.overall_status) != "OverallStatus.FAILED"
    assert "感謝する" in _predicates(response)
    assert not any(
        item.intent_type == "exception"
        for item in response.meaning_graph.propositions
    )


def test_optional_fix_end_when_no_extra_change_needed(engine):
    response = _analyze(engine, "追加修正が不要なら終了してください。")
    predicates = _predicates(response)
    reading = response.meaning_graph.reading_analysis

    assert str(response.overall_status) == "OverallStatus.COMPLETE"
    assert "終了する" in predicates
    assert "条件とする" not in predicates
    assert "要求する" not in predicates
    assert _condition_scopes(response)
    assert not any(
        item.predicate == "不要" for item in response.meaning_graph.propositions
    )


def test_preserve_existing_positive_examples_prohibition(engine):
    response = _analyze(engine, "既存の正例を壊さないで。")
    reading = response.meaning_graph.reading_analysis

    assert str(response.overall_status) == "OverallStatus.COMPLETE"
    assert "壊す" in _predicates(response)
    assert any(item.operator_type == "negation" for item in reading.scope_operators)
    assert "条件とする" not in _predicates(response)


def test_no_extra_processing_prohibition(engine):
    response = _analyze(engine, "余計な加工はしないでください。")
    reading = response.meaning_graph.reading_analysis

    assert str(response.overall_status) == "OverallStatus.COMPLETE"
    assert any(
        item.intent_type == "prohibition"
        for item in response.meaning_graph.propositions
    )
    assert any(item.operator_type == "negation" for item in reading.scope_operators)
    assert "条件とする" not in _predicates(response)


def test_completion_requires_confirmation_limit(engine):
    response = _analyze(engine, "確認しない限り完了ではない。")
    reading = response.meaning_graph.reading_analysis

    assert str(response.overall_status) == "OverallStatus.COMPLETE"
    assert "確認する" in _predicates(response)
    assert _condition_scopes(response)
    assert not response.meaning_graph.unresolved
    assert not any(
        item.get("type") == "reading_scope_target"
        for item in response.meaning_graph.unresolved
    )


def test_concessive_publish_despite_failure(engine):
    response = _analyze(engine, "失敗したにもかかわらず公開する。")
    reading = response.meaning_graph.reading_analysis
    predicates = _predicates(response)

    assert str(response.overall_status) != "OverallStatus.FAILED"
    assert "公開する" in predicates
    assert any(
        item.semantic_value == "concessive_condition"
        for item in reading.scope_operators
    )
    assert "実行する" not in predicates
    assert "関わる" not in predicates


def test_contrastive_exception_clause(engine):
    response = _analyze(engine, "公開する。ただし障害なら止める。")
    reading = response.meaning_graph.reading_analysis
    predicates = _predicates(response)

    assert str(response.overall_status) == "OverallStatus.COMPLETE"
    assert "公開する" in predicates
    assert "止める" in predicates
    assert "例外とする" not in predicates
    assert _condition_scopes(response)


def test_deploy_occasion_condition(engine):
    response = _analyze(engine, "デプロイの際は確認する。")

    assert str(response.overall_status) == "OverallStatus.COMPLETE"
    assert "確認する" in _predicates(response)
    assert _condition_scopes(response)


def test_nested_conditional_approval_gate(engine):
    response = _analyze(engine, "もし雨なら、承認された場合だけ中止する。")

    assert str(response.overall_status) == "OverallStatus.COMPLETE"
    assert "中止する" in _predicates(response)
    assert len(_condition_scopes(response)) >= 2


def test_conjoined_conditions_before_completion(engine):
    response = _analyze(engine, "テストが通って、かつレビューが終わったら完了。")

    assert str(response.overall_status) == "OverallStatus.COMPLETE"
    assert any(
        item.intent_type == "completion_criteria"
        for item in response.meaning_graph.propositions
    )
    assert _condition_scopes(response)
    assert "条件とする" not in _predicates(response)


def test_sore_object_reporting_request(engine):
    response = _analyze(
        engine,
        "田中さんが来た。彼は本を読んだ。それを報告してください。",
    )
    resolution = next(
        item for item in response.references if item.expression == "それ"
    )

    assert resolution.selected == "本"
    assert str(response.overall_status) != "OverallStatus.FAILED"
    assert "報告する" in _predicates(response)
    assert "要求する" not in _predicates(response)


def test_retry_keeps_failure_premise_observation(engine):
    response = _analyze(engine, "失敗したら再試行してください。")
    predicates = _predicates(response)

    assert "再試行する" in predicates
    assert "失敗する" in predicates
    assert "条件とする" not in predicates
    assert _condition_scopes(response)


def test_restrictive_completion_quantifier_recorded(engine):
    response = _analyze(engine, "全件が通った場合のみ完了です。")
    reading = response.meaning_graph.reading_analysis
    scopes = {
        (item.operator_type, item.semantic_value)
        for item in reading.scope_operators
    }

    assert str(response.overall_status) == "OverallStatus.COMPLETE"
    assert any(
        item.intent_type == "completion_criteria"
        for item in response.meaning_graph.propositions
    )
    assert ("quantifier", "restrictive") in scopes
    assert ("condition", "premise_condition") in scopes


def test_rule_trigger_extraction_tolerates_unparseable_pattern():
    """rule_engine._extract_proven_triggers はルール索引のトリガー抽出用。
    壊れた正規表現は空タプルを返し analyze 結果は変えない（誤解析の隠蔽ではない）。
    semantic_data_runtime の except Exception は materialize 失敗時に store を閉じたうえで再送出する。"""
    from deterministic_japanese_parser_mcp.rule_engine import _extract_proven_triggers

    assert _extract_proven_triggers("(?P<broken") == ()
