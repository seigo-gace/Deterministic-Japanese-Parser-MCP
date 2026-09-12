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


def test_negation_targets_only_the_modified_predicate(engine):
    response = _analyze(engine, "設定を変更せず保存した。")
    reading = response.meaning_graph.reading_analysis
    frames = {frame.predicate: frame for frame in reading.predicate_frames}

    change = frames["変更する"]
    save = frames["保存する"]
    assert change.polarity == "negative"
    assert save.polarity == "positive"

    negation = next(
        item for item in reading.scope_operators
        if item.operator_type == "negation"
    )
    assert negation.target_frame_ids == [change.frame_id]


def test_condition_targets_only_the_consequent_predicate(engine):
    response = _analyze(engine, "テストが通ったら、結果を保存する。")
    reading = response.meaning_graph.reading_analysis
    save = next(
        frame for frame in reading.predicate_frames
        if frame.predicate == "保存する"
    )
    condition = next(
        item for item in reading.scope_operators
        if item.operator_type == "condition"
        and item.semantic_value == "event_condition"
    )

    assert condition.target_frame_ids == [save.frame_id]


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


def test_in_sentence_reason_marker_connects_predicate_clauses(engine):
    response = _analyze(engine, "雨が降ったので試合は延期された。")
    reading = response.meaning_graph.reading_analysis
    relation = reading.discourse_relations[0]

    assert [frame.predicate for frame in reading.predicate_frames] == [
        "降る",
        "延期する",
    ]
    assert relation.relation == "causes"
    assert relation.marker == "ので"
    assert relation.source_clause_id != relation.target_clause_id


def test_in_sentence_contrast_marker_connects_predicate_clauses(engine):
    response = _analyze(engine, "A案は速いが、B案は安全だ。")
    reading = response.meaning_graph.reading_analysis
    relation = reading.discourse_relations[0]

    assert [frame.predicate for frame in reading.predicate_frames] == [
        "速い",
        "安全",
    ]
    assert relation.relation == "contrasts_with"
    assert relation.marker in {"が", "が、"}
    assert relation.source_clause_id != relation.target_clause_id


def test_passive_agent_marker_is_not_a_predicate(engine):
    response = _analyze(engine, "設定が開発者によって変更された。")
    frame = response.meaning_graph.reading_analysis.predicate_frames[0]

    assert frame.predicate == "変更する"
    assert frame.voice == ["passive"]
    assert {(item.role, item.value, item.case_marker) for item in frame.arguments} == {
        ("patient", "設定", "が"),
        ("agent", "開発者", "によって"),
    }


def test_honorific_request_creates_executable_task(engine):
    response = _analyze(
        engine,
        "田中さんが資料をご確認ください。",
        external=True,
    )

    assert response.execution_allowed
    assert response.task_graph.tasks
    task = response.task_graph.tasks[0]
    assert task.intent_type == "request"
    assert task.target == "資料"


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


def test_negated_te_kudasai_keeps_matrix_verb_as_proposition(engine):
    response = _analyze(engine, "行かないでください。")
    proposition = response.meaning_graph.propositions[0]
    frames = response.meaning_graph.reading_analysis.predicate_frames

    assert proposition.predicate == "行く"
    assert frames[0].predicate == "行く"
    assert "下さる" not in proposition.predicate
    assert all(frame.predicate != "下さる" for frame in frames)


def test_te_kudasai_keeps_causative_matrix_verb(engine):
    response = _analyze(engine, "ドアを開けてください。")
    matrix = next(
        item
        for item in response.meaning_graph.propositions
        if item.intent_type == "observation"
    )
    frame = response.meaning_graph.reading_analysis.predicate_frames[0]

    assert matrix.predicate == "開ける"
    assert frame.predicate == "開ける"


def test_gratitude_expression_yields_proposition(engine):
    response = _analyze(engine, "本当にありがとう。")

    assert str(response.overall_status) != "FAILED"
    assert response.meaning_graph.propositions
    gratitude = response.meaning_graph.propositions[0]
    assert gratitude.predicate == "感謝する"
    assert gratitude.speech_act == "gratitude"


def test_conditional_clause_keeps_matrix_observation_proposition(engine):
    response = _analyze(engine, "もし雨なら中止する。")
    predicates = {
        item.predicate
        for item in response.meaning_graph.propositions
        if item.intent_type == "observation"
    }

    assert "中止する" in predicates
    assert "実行する" not in {
        item.predicate for item in response.meaning_graph.propositions
    }
    assert "条件とする" not in {
        item.predicate for item in response.meaning_graph.propositions
    }
    assert any(
        item.operator_type == "condition"
        for item in response.meaning_graph.reading_analysis.scope_operators
    )


def test_copula_identification_is_not_failed_without_antecedent(engine):
    response = _analyze(engine, "これはペンです。")

    assert str(response.overall_status) != "FAILED"
    assert any(
        item.predicate == "ペン"
        for item in response.meaning_graph.propositions
    )


def _has_question_meta_proposition(propositions) -> bool:
    return any(
        item.intent_type == "question"
        or item.predicate in {"質問する", "実行可能性を質問する"}
        for item in propositions
    )


@pytest.mark.parametrize(
    "text",
    [
        "それは何ですか",
        "あの人は誰ですか",
        "この端末で処理できますか。",
        "今週中の修正は可能ですか。",
    ],
)
def test_interrogatives_do_not_emit_question_meta_propositions(engine, text):
    response = _analyze(engine, text, external=True)
    reading = response.meaning_graph.reading_analysis

    assert str(response.overall_status) != "FAILED"
    assert not _has_question_meta_proposition(response.meaning_graph.propositions)
    assert any(item.operator_type == "question" for item in reading.scope_operators)
    assert not response.execution_allowed


def test_conditional_connection_omits_condition_proposition(engine):
    response = _analyze(engine, "もし雨なら中止する。")
    predicates = {item.predicate for item in response.meaning_graph.propositions}

    assert "中止する" in predicates
    assert "実行する" not in predicates
    assert "条件とする" not in predicates
    assert any(
        item.operator_type == "condition"
        for item in response.meaning_graph.reading_analysis.scope_operators
    )


def test_deploy_completion_criteria_sentence_is_complete(engine):
    response = _analyze(engine, "デプロイ確認ができたら完了。")

    assert response.overall_status.value == "COMPLETE"
    assert any(
        item.intent_type == "completion_criteria"
        for item in response.meaning_graph.propositions
    )
    assert not any(
        item.get("type") == "reading_scope_target"
        for item in response.meaning_graph.unresolved
    )


@pytest.mark.parametrize(
    "text",
    [
        "この端末で処理できますか。",
        "今週中の修正は可能ですか。",
    ],
)
def test_capability_question_keeps_pragmatic_marker(engine, text):
    response = _analyze(engine, text, external=True)

    matching = [
        item
        for item in response.meaning_graph.propositions
        if "pragmatic.capability_question" in item.pragmatic_markers
        and item.speech_act == "capability_question"
    ]
    assert matching
    assert not response.execution_allowed


def test_invariant_preserve_phrase_is_not_failed(engine):
    response = _analyze(engine, "この構造を不変条件とする。")

    assert str(response.overall_status) != "FAILED"
    assert any(
        item.intent_type == "preserve"
        for item in response.meaning_graph.propositions
    )


def test_discourse_pronoun_resolves_to_prior_subject(engine):
    response = _analyze(engine, "田中さんが来た。彼は本を読んだ。")
    resolution = next(
        item for item in response.references if item.expression == "彼"
    )

    assert resolution.selected == "田中さん"
    assert resolution.status.value == "RESOLVED"


def test_conversation_context_resolves_kare(engine):
    response = engine.analyze(AnalyzeRequest(
        original_text="彼は本を読んだ",
        conversation_context=["田中さん"],
    ))
    resolution = next(
        item for item in response.references if item.expression == "彼"
    )

    assert resolution.selected == "田中さん"


def test_same_request_resolves_sore_to_discourse_antecedent(engine):
    response = _analyze(engine, "ペンを見て。それは何ですか。")
    resolution = next(
        item for item in response.references if item.expression == "それ"
    )

    assert resolution.selected == "ペン"
    assert str(response.overall_status) != "FAILED"
    assert not _has_question_meta_proposition(response.meaning_graph.propositions)


def test_conversation_context_resolves_sore(engine):
    response = engine.analyze(AnalyzeRequest(
        original_text="それをください",
        conversation_context=["ペン"],
    ))
    resolution = next(
        item for item in response.references if item.expression == "それ"
    )

    assert resolution.selected == "ペン"
