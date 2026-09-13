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
    toru = [
        item
        for item in response.meaning_graph.propositions
        if item.predicate in {"通う", "通る"}
    ]

    assert str(response.overall_status) == "OverallStatus.COMPLETE"
    assert completion
    assert not response.meaning_graph.unresolved
    assert len(toru) == 1
    assert toru[0].predicate == "通る"
    assert toru[0].sense_id == "pass.test"
    assert toru[0].sense_label == "test_or_validation_pass"


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
    toru = [
        item
        for item in response.meaning_graph.propositions
        if item.predicate in {"通う", "通る"}
        or "通" in (item.surface_predicate or "")
    ]
    assert toru
    assert all(item.predicate == "通る" for item in toru)
    assert all(item.sense_id == "pass.test" for item in toru)
    assert all(item.sense_label == "test_or_validation_pass" for item in toru)


def test_test_pass_plain_form(engine):
    response = _analyze(engine, "テストが通る")
    toru = next(
        item
        for item in response.meaning_graph.propositions
        if item.predicate in {"通う", "通る"}
    )

    assert toru.predicate == "通る"
    assert toru.sense_id == "pass.test"
    assert toru.sense_label == "test_or_validation_pass"


def test_commute_toru_unchanged(engine):
    response = _analyze(engine, "毎日学校に通う")
    toru = next(
        item
        for item in response.meaning_graph.propositions
        if item.predicate in {"通う", "通る"}
    )
    frames = response.meaning_graph.reading_analysis.predicate_frames

    assert toru.predicate == "通う"
    assert toru.sense_id != "pass.test"
    assert frames[0].predicate == "通う"


def test_toru_disambiguation_regression_sentences(engine):
    cases = {
        "本を読む": "読む",
        "雨が降る": "降る",
        "もし雨なら中止する。": "中止する",
        "やめてください": "やめる",
        "ドアを開けてください": "開ける",
    }
    for text, expected_predicate in cases.items():
        response = _analyze(engine, text)
        predicates = _predicates(response)
        assert expected_predicate in predicates
        assert "通う" not in predicates or text.startswith("毎日")


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
    frames = [
        item.predicate
        for item in reading.predicate_frames
        if item.surface_predicate
        and "通" in item.surface_predicate
    ]

    assert str(response.overall_status) == "OverallStatus.COMPLETE"
    assert any(
        item.intent_type == "completion_criteria"
        for item in response.meaning_graph.propositions
    )
    assert ("quantifier", "restrictive") in scopes
    assert ("condition", "premise_condition") in scopes
    assert frames == ["通る"]


@pytest.mark.parametrize(
    "text",
    [
        "検査が通った",
        "ビルドが通った",
    ],
)
def test_validation_subject_pass_toru_reading(engine, text):
    response = _analyze(engine, text)
    toru = next(
        item
        for item in response.meaning_graph.propositions
        if item.predicate in {"通う", "通る"}
    )
    frame = next(
        item
        for item in response.meaning_graph.reading_analysis.predicate_frames
        if "通" in item.surface_predicate
    )

    assert toru.predicate == "通る"
    assert toru.sense_id == "pass.test"
    assert toru.sense_label == "test_or_validation_pass"
    assert frame.predicate == "通る"


@pytest.mark.parametrize(
    ("text", "expected_predicates"),
    [
        ("子供が学校に行く。", {"行く"}),
        ("窓を閉めてください。", {"閉める"}),
        ("食べないでください。", {"食べる"}),
        ("電車に乗る。", {"乗る"}),
        ("風が吹く。", {"吹く"}),
        ("火が消える。", {"消える"}),
        ("電話が鳴る。", {"鳴る"}),
        ("宿題を忘れないでください。", {"忘れる"}),
        ("誰が来ましたか。", {"来る", "誰"}),
        ("何を食べますか。", {"食べる", "何"}),
        ("どこへ行きますか。", {"行く"}),
        ("この本は面白い。", {"面白い"}),
    ],
)
def test_daily_unknown_sentences_stay_complete_without_meta(
    engine,
    text,
    expected_predicates,
):
    response = _analyze(engine, text)
    reading = response.meaning_graph.reading_analysis

    assert str(response.overall_status) != "OverallStatus.FAILED"
    assert expected_predicates <= _predicates(response)
    assert "条件とする" not in _predicates(response)
    assert "実行する" not in _predicates(response)
    assert not _has_question_meta(response) or any(
        item.operator_type == "question" for item in reading.scope_operators
    )


def test_book_purchase_opens_discourse_sore(engine):
    response = _analyze(engine, "本を買った。それを開いた。")
    resolution = next(
        item for item in response.references if item.expression == "それ"
    )

    assert resolution.selected == "本"
    assert "開く" in _predicates(response)
    assert str(response.overall_status) == "OverallStatus.COMPLETE"


def test_kanojo_discourse_and_copula_complete(engine):
    response = _analyze(engine, "彼女は学生です。彼女は本を読む。")
    resolutions = {
        item.expression: item.selected
        for item in response.references
    }

    assert str(response.overall_status) == "OverallStatus.COMPLETE"
    assert resolutions == {"彼女": "彼女"}
    assert not response.meaning_graph.unresolved
    assert {"学生", "読む"} <= _predicates(response)


def test_conditional_time_invitation_no_condition_meta(engine):
    response = _analyze(engine, "もし時間があれば来てください。")

    assert str(response.overall_status) == "OverallStatus.COMPLETE"
    assert "来る" in _predicates(response)
    assert "条件とする" not in _predicates(response)
    assert _condition_scopes(response)


def test_rain_cancellation_causal_discourse(engine):
    response = _analyze(engine, "昨日雨が降ったから試合は中止です。")

    assert str(response.overall_status) != "OverallStatus.FAILED"
    assert {"降る", "中止"} <= _predicates(response)


def test_triple_nested_conditional_gate_records_three_scopes(engine):
    response = _analyze(
        engine,
        "もし雨なら、承認された場合だけ、責任者がいるときに中止する。",
    )
    reading = response.meaning_graph.reading_analysis
    conditions = _condition_scopes(response)

    assert str(response.overall_status) == "OverallStatus.COMPLETE"
    assert "中止する" in _predicates(response)
    assert len(conditions) == 3
    assert not response.meaning_graph.unresolved
    assert "条件とする" not in _predicates(response)


def test_jikan_areba_invitation_without_spurious_are(engine):
    response = _analyze(engine, "時間あれば来てください。")
    reading = response.meaning_graph.reading_analysis

    assert str(response.overall_status) == "OverallStatus.COMPLETE"
    assert _predicates(response) == {"来る"}
    assert _condition_scopes(response)
    assert not response.references
    assert not response.meaning_graph.unresolved
    assert "有る" not in _predicates(response)


def test_sore_imperative_with_conversation_context(engine):
    response = _analyze(engine, "それ、見て。", context=["報告書"])
    resolution = next(
        item for item in response.references if item.expression == "それ"
    )

    assert resolution.selected == "報告書"
    assert "見る" in _predicates(response)
    assert str(response.overall_status) == "OverallStatus.COMPLETE"


@pytest.mark.parametrize(
    "text",
    [
        "件数が通った。",
        "ケースが通った。",
    ],
)
def test_count_and_case_pass_toru_sense(engine, text):
    response = _analyze(engine, text)
    toru = next(
        item
        for item in response.meaning_graph.propositions
        if item.predicate in {"通う", "通る"}
    )

    assert toru.predicate == "通る"
    assert toru.sense_id == "pass.test"
    assert toru.sense_label == "test_or_validation_pass"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("電車に乗る。", "乗る"),
        ("電車で学校に通う。", "通う"),
        ("橋を渡る。", "渡る"),
    ],
)
def test_motion_verbs_are_not_collapsed_to_toru(engine, text, expected):
    response = _analyze(engine, text)
    predicates = _predicates(response)

    assert expected in predicates
    assert "通る" not in predicates or expected == "通う"


@pytest.mark.parametrize(
    "text",
    [
        "食べないで。",
        "行かないで。",
    ],
)
def test_casual_negated_te_form_keeps_matrix_verb(engine, text):
    response = _analyze(engine, text)
    reading = response.meaning_graph.reading_analysis

    assert str(response.overall_status) == "OverallStatus.COMPLETE"
    assert any(item.operator_type == "negation" for item in reading.scope_operators)
    assert "条件とする" not in _predicates(response)


def test_window_close_elided_imperative(engine):
    response = _analyze(engine, "窓閉めて。")

    assert str(response.overall_status) == "OverallStatus.COMPLETE"
    assert "閉める" in _predicates(response)


def _sense_map(response) -> dict[str, tuple[str | None, str | None]]:
    return {
        item.predicate: (item.sense_id, item.sense_label)
        for item in response.meaning_graph.propositions
    }


@pytest.mark.parametrize(
    ("text", "expected_predicates", "forbidden"),
    [
        ("時間あれば来て。", {"来る"}, {"条件とする", "有る"}),
        ("窓閉めて。", {"閉める"}, set()),
        ("もう帰っていい？", {"帰る", "良い"}, {"質問する"}),
        ("先に行っといて。", {"行く"}, set()),
        ("子供に本を読ませる。", {"読ませる"}, set()),
        ("窓が開けられた。", {"開ける"}, set()),
        ("この本は読める。", {"読む"}, set()),
        ("先生がいらっしゃいました。", {"いらっしゃる"}, set()),
        ("コーヒーを召し上がってください。", {"召し上がる"}, set()),
        ("資料を拝見しました。", {"拝見する"}, set()),
        ("雨が降っている。", {"降る"}, set()),
        ("鍵をかけてしまった。", {"かける"}, set()),
        ("明日は晴れるかもしれない。", {"晴れる"}, {"知れる"}),
        ("彼は来るはずだ。", {"来る"}, {"筈", "参照する"}),
        ("田中さんは「行かないで」と言った。", {"言う", "行く"}, set()),
        ("疲れたから休む。", {"疲れる", "休む"}, {"条件とする", "質問する"}),
        ("呼んだのに来ない。", {"呼ぶ", "来る"}, set()),
        ("弟に本をあげる。", {"上げる"}, set()),
        ("友達が本をくれた。", {"呉れる"}, set()),
        ("水しか飲まない。", {"飲む"}, {"条件とする", "質問する"}),
        ("これだけは守って。", {"守る"}, {"例外とする", "参照する"}),
        ("電車よりバスが速い。", {"速い"}, set()),
        ("医者が患者を診る。", {"診る"}, {"見る"}),
        ("音楽を聴く。", {"聴く"}, {"聞く"}),
        ("話を聞く。", {"聞く"}, set()),
        ("ドアが開く。", {"開く"}, set()),
        ("ドアを開ける。", {"開ける"}, set()),
        ("目を覚ます。", {"覚ます"}, set()),
        ("終わったら連絡する。", {"終わる", "連絡する"}, set()),
        ("見に行ってもいい？", {"見る", "行く", "良い"}, set()),
        ("行ってくる。", {"行く"}, set()),
        ("昨日買った本を読んだ。", {"買う", "読む"}, set()),
        ("行かないでください", {"行く"}, set()),
        ("本当にありがとう", {"感謝する"}, set()),
        ("これはペンです", {"ペン"}, set()),
    ],
)
def test_colloquial_and_multisense_reading_audit(
    engine,
    text,
    expected_predicates,
    forbidden,
):
    response = _analyze(engine, text)
    predicates = _predicates(response)
    reading = response.meaning_graph.reading_analysis

    assert str(response.overall_status) != "OverallStatus.FAILED"
    assert reading.status.value == "RESOLVED"
    assert expected_predicates <= predicates
    assert not (forbidden & predicates)
    assert "条件とする" not in predicates
    assert "実行する" not in predicates
    assert not response.meaning_graph.unresolved


def test_sore_mite_colloquial_without_reference_meta(engine):
    response = _analyze(engine, "それ見て。", context=["報告書"])
    predicates = _predicates(response)
    resolution = next(
        item for item in response.references if item.expression == "それ"
    )

    assert predicates == {"見る"}
    assert "参照する" not in predicates
    assert resolution.selected == "報告書"


def test_japanese_potential_skill_topic(engine):
    response = _analyze(engine, "日本語が話せる。")
    frame = response.meaning_graph.reading_analysis.predicate_frames[0]

    assert "話す" in _predicates(response)
    assert {(item.role, item.value) for item in frame.arguments} == {
        ("topic", "日本語"),
    }


def test_medical_examine_and_music_listen_senses(engine):
    examine = _analyze(engine, "医者が患者を診る。")
    listen = _analyze(engine, "音楽を聴く。")
    senses = _sense_map(examine)
    listen_senses = _sense_map(listen)

    assert senses["診る"] == ("examine.medical", "medical_examination")
    assert listen_senses["聴く"] == ("listen.audio", "listen_to_audio_or_music")


def test_shika_exclusive_quantifier_with_negation(engine):
    response = _analyze(engine, "水しか飲まない。")
    reading = response.meaning_graph.reading_analysis
    scopes = {
        (item.operator_type, item.semantic_value)
        for item in reading.scope_operators
    }
    drink = next(
        item
        for item in response.meaning_graph.propositions
        if item.predicate == "飲む"
    )

    assert str(response.overall_status) == "OverallStatus.COMPLETE"
    assert scopes >= {("negation", "negation"), ("quantifier", "exclusive")}
    assert drink.polarity == "negative"
    assert "条件とする" not in _predicates(response)
    assert not _has_question_meta(response)


def test_permission_te_mo_i_is_not_concessive_condition(engine):
    response = _analyze(engine, "見に行ってもいい？")
    reading = response.meaning_graph.reading_analysis
    scopes = {
        (item.operator_type, item.semantic_value)
        for item in reading.scope_operators
    }
    predicates = _predicates(response)

    assert str(response.overall_status) == "OverallStatus.COMPLETE"
    assert scopes >= {("modality", "permission"), ("question", "interrogative")}
    assert ("condition", "concessive_condition") not in scopes
    assert {"見る", "行く", "良い"} <= predicates
    assert [frame.predicate for frame in reading.predicate_frames] == [
        "見る",
        "行く",
        "良い",
    ]


@pytest.mark.parametrize(
    "text",
    [
        "呼んだのに来ない。",
        "水しか飲まない。",
        "疲れたから休む。",
        "行かないでください",
    ],
)
def test_permission_te_mo_regression_sentences(engine, text):
    response = _analyze(engine, text)
    reading = response.meaning_graph.reading_analysis
    scopes = {
        (item.operator_type, item.semantic_value)
        for item in reading.scope_operators
    }

    assert str(response.overall_status) != "OverallStatus.FAILED"
    if text == "呼んだのに来ない。":
        assert ("condition", "concessive_condition") not in scopes
        assert any(
            item.relation == "contrasts_with" and item.marker == "のに"
            for item in reading.discourse_relations
        )
        assert {"呼ぶ", "来る"} <= _predicates(response)
    if text == "水しか飲まない。":
        assert scopes >= {("negation", "negation"), ("quantifier", "exclusive")}
    if text == "疲れたから休む。":
        assert any(
            item.relation == "causes" and item.marker == "から"
            for item in reading.discourse_relations
        )
    if text == "行かないでください":
        assert ("negation", "negation") in scopes
        assert "行く" in _predicates(response)


def test_kara_causal_discourse_within_single_clause(engine):
    response = _analyze(engine, "疲れたから休む。")
    reading = response.meaning_graph.reading_analysis
    relation = reading.discourse_relations[0]

    assert [frame.predicate for frame in reading.predicate_frames] == [
        "疲れる",
        "休む",
    ]
    assert relation.relation == "causes"
    assert relation.marker == "から"
    assert {"疲れる", "休む"} <= _predicates(response)
    assert "条件とする" not in _predicates(response)
    assert not _has_question_meta(response)


@pytest.mark.parametrize(
    "text",
    [
        "本を読む",
        "雨が降る",
        "医者が患者を診る。",
        "音楽を聴く。",
        "毎日学校に通う",
        "テストが通る",
        "ドアを開ける。",
        "ドアが開く。",
        "行かないでください",
    ],
)
def test_reading_regression_after_shika_and_kara_fixes(engine, text):
    response = _analyze(engine, text)

    assert str(response.overall_status) != "OverallStatus.FAILED"
    assert "条件とする" not in _predicates(response)
    assert "質問する" not in _predicates(response)


def test_commute_and_conjoined_review_agents(engine):
    commute = _analyze(engine, "毎日学校に通う")
    commute_frame = commute.meaning_graph.reading_analysis.predicate_frames[0]
    joined = _analyze(engine, "テストが通って、かつレビューが終わったら完了。")
    end_frame = next(
        frame
        for frame in joined.meaning_graph.reading_analysis.predicate_frames
        if frame.predicate == "終わる"
    )

    assert commute_frame.predicate == "通う"
    assert {(item.role, item.value) for item in commute_frame.arguments} == {
        ("recipient", "学校"),
    }
    assert {(item.role, item.value) for item in end_frame.arguments} == {
        ("agent", "レビュー"),
    }


def test_regression_baseline_sentences_remain_stable(engine):
    cases = {
        "本を読む": "読む",
        "雨が降る": "降る",
        "やめてください": "やめる",
        "ドアを開けてください": "開ける",
        "もし雨なら中止する": "中止する",
        "毎日学校に通う": "通う",
        "電車で学校に通う": "通う",
        "電車に乗る": "乗る",
        "田中さんが来た。彼は本を読んだ。": "読む",
    }
    for text, needle in cases.items():
        response = _analyze(engine, text)
        assert needle in _predicates(response)
        assert str(response.overall_status) != "OverallStatus.FAILED"


def test_rule_trigger_extraction_tolerates_unparseable_pattern():
    """rule_engine._extract_proven_triggers はルール索引のトリガー抽出用。
    壊れた正規表現は空タプルを返し analyze 結果は変えない（誤解析の隠蔽ではない）。
    semantic_data_runtime の except Exception は materialize 失敗時に store を閉じたうえで再送出する。"""
    from deterministic_japanese_parser_mcp.rule_engine import _extract_proven_triggers

    assert _extract_proven_triggers("(?P<broken") == ()
