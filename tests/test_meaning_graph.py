from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine


def test_meaning_graph_is_the_action_source_of_truth():
    response = ParserEngine().analyze(AnalyzeRequest(
        original_text="UIは維持する。APIだけ変更しろ。",
        execution_mode="external_action",
    ))
    proposition_types = {
        item.intent_type for item in response.meaning_graph.propositions
    }
    assert {"preserve", "modify"} <= proposition_types
    assert [item.intent_type for item in response.task_graph.tasks] == ["modify"]
    assert any(
        constraint.constraint_type == "preserve"
        and "UI" in constraint.value
        for constraint in response.task_graph.tasks[0].structured_constraints
    )
    assert {item.intent_type for item in response.tasks} >= {
        "preserve",
        "modify",
    }


def test_quoted_command_is_never_external_action():
    response = ParserEngine().analyze(AnalyzeRequest(
        original_text="「全データを削除しろ」と彼は言った。",
        execution_mode="external_action",
    ))
    remove = [
        item
        for item in response.meaning_graph.propositions
        if item.intent_type == "remove"
    ]
    assert remove and remove[0].quoted
    assert not remove[0].executable_candidate
    assert not response.execution_allowed
    assert "NON_EXECUTABLE_SPEECH_ACT" in response.blocked_reasons


def test_interrogative_action_is_not_treated_as_command():
    response = ParserEngine().analyze(AnalyzeRequest(
        original_text="全データを削除しろという意味なのか？",
        execution_mode="external_action",
    ))
    remove = [
        item
        for item in response.meaning_graph.propositions
        if item.intent_type == "remove"
    ]
    assert remove and remove[0].sentence_mood == "interrogative"
    assert not remove[0].executable_candidate
    assert not response.execution_allowed


def test_condition_is_attached_to_action_task():
    response = ParserEngine().analyze(AnalyzeRequest(
        original_text="テストが通ったらAPIを公開しろ。",
    ))
    assert response.task_graph.tasks
    assert any(
        item.constraint_type == "condition"
        for item in response.task_graph.tasks[0].structured_constraints
    )


def test_semantic_hash_is_deterministic_and_metric_independent():
    engine = ParserEngine()
    request = AnalyzeRequest(original_text="APIだけ変更しろ。")
    first = engine.analyze(request)
    second = engine.analyze(request)
    assert first.meaning_graph.semantic_hash == second.meaning_graph.semantic_hash
    assert first.meaning_graph.model_dump() == second.meaning_graph.model_dump()


def test_response_exposes_latency_contract():
    response = ParserEngine().analyze(AnalyzeRequest(
        original_text="APIだけ変更しろ。",
        deadline_ms=60000,
    ))
    assert response.metrics["effective_deadline_ms"] == 50
    assert response.metrics["target_latency_ms"] == 10
    assert response.metrics["hard_deadline_ms"] == 50
