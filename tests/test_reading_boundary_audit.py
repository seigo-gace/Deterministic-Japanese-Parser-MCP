import pytest

from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine


@pytest.fixture(scope="module")
def engine() -> ParserEngine:
    return ParserEngine()


def _analyze(engine: ParserEngine, text: str):
    return engine.analyze(AnalyzeRequest(original_text=text))


def _scopes(response, operator_type: str | None = None) -> set[tuple[str, str]]:
    reading = response.meaning_graph.reading_analysis
    values = {
        (item.operator_type, item.semantic_value)
        for item in reading.scope_operators
    }
    if operator_type is None:
        return values
    return {item for item in values if item[0] == operator_type}


def _voices(response) -> set[str]:
    reading = response.meaning_graph.reading_analysis
    return {
        voice
        for frame in reading.predicate_frames
        for voice in frame.voice
    }


def _relations(response) -> set[str]:
    reading = response.meaning_graph.reading_analysis
    return {item.relation for item in reading.discourse_relations}


@pytest.mark.parametrize(
    "text",
    [
        "まず確認する。",
        "ずっと待つ。",
        "危ない道を歩く。",
        "少ない人数で進める。",
        "ぬいぐるみを買う。",
        "来るはずだ。",
    ],
)
def test_lexical_surfaces_do_not_create_negation(engine, text):
    response = _analyze(engine, text)

    assert str(response.overall_status) != "OverallStatus.FAILED"
    assert not _scopes(response, "negation")


@pytest.mark.parametrize("text", ["確認せず進む。", "今日は行かない。", "何も知らぬ。"])
def test_true_negation_is_preserved(engine, text):
    response = _analyze(engine, text)

    assert _scopes(response, "negation")


@pytest.mark.parametrize(
    "text",
    [
        "駅まで歩く。",
        "5時まで働く。",
        "ここでも使える。",
        "水でも飲む。",
        "たらこを食べる。",
        "さよならを言う。",
        "例えば、猫を挙げる。",
        "国際会議を開く。",
        "友達と、映画を見る。",
    ],
)
def test_lexical_or_case_surfaces_do_not_create_condition_scope(engine, text):
    response = _analyze(engine, text)

    assert str(response.overall_status) != "OverallStatus.FAILED"
    assert not _scopes(response, "condition")


@pytest.mark.parametrize(
    "text",
    [
        "食べたら帰る。",
        "必要なら進む。",
        "ボタンを押すと、画面が開く。",
        "終わるまで待つ。",
    ],
)
def test_true_conditions_are_preserved(engine, text):
    response = _analyze(engine, text)

    assert _scopes(response, "condition")


@pytest.mark.parametrize(
    "text",
    [
        "入ってもよろしいですか？",
        "触っても大丈夫ですか？",
        "ここに置いても構いませんか？",
    ],
)
def test_permission_variants_are_permission_not_concessive(engine, text):
    response = _analyze(engine, text)
    scopes = _scopes(response)

    assert str(response.overall_status) != "OverallStatus.FAILED"
    assert ("modality", "permission") in scopes
    assert ("question", "interrogative") in scopes
    assert ("condition", "concessive_condition") not in scopes


def test_demo_ii_acceptability_is_not_concessive_condition(engine):
    response = _analyze(engine, "これでもいい？")
    scopes = _scopes(response)

    assert ("modality", "permission") in scopes
    assert ("condition", "concessive_condition") not in scopes


@pytest.mark.parametrize(
    ("text", "expected_hearsay"),
    [
        ("雨が降りそうだ。", False),
        ("天気予報によると雨が降るそうだ。", True),
        ("彼は男らしい人だ。", False),
        ("素晴らしい景色だ。", False),
        ("かわいそうだ。", False),
        ("彼は来るらしい。", True),
    ],
)
def test_hearsay_markers_require_grammatical_use(engine, text, expected_hearsay):
    response = _analyze(engine, text)
    has_hearsay = ("modality", "hearsay") in _scopes(response)

    assert has_hearsay is expected_hearsay


@pytest.mark.parametrize(
    ("text", "expected_desire"),
    [
        ("猫みたいだ。", False),
        ("映画を見たい。", True),
    ],
)
def test_tai_desire_does_not_match_mitai(engine, text, expected_desire):
    response = _analyze(engine, text)
    has_desire = ("modality", "desire") in _scopes(response)

    assert has_desire is expected_desire


def test_suru_nara_is_condition_not_prohibition(engine):
    response = _analyze(engine, "実行するなら確認する。")
    scopes = _scopes(response)

    assert _scopes(response, "condition")
    assert ("modality", "prohibition") not in scopes


def test_true_suru_na_prohibition_is_preserved(engine):
    response = _analyze(engine, "実行するな。")

    assert ("modality", "prohibition") in _scopes(response)


@pytest.mark.parametrize("text", ["以上のことから結論を出す。", "以下の通りです。"])
def test_discourse_ijo_ika_are_not_numeric_quantifiers(engine, text):
    response = _analyze(engine, text)

    assert not _scopes(response, "quantifier")


@pytest.mark.parametrize(
    ("text", "semantic_value"),
    [
        ("3個以上必要だ。", "lower_bound"),
        ("10個以下にする。", "upper_bound"),
    ],
)
def test_numeric_ijo_ika_keep_quantifier_scope(engine, text, semantic_value):
    response = _analyze(engine, text)

    assert ("quantifier", semantic_value) in _scopes(response)


def test_rareru_potential_is_not_forced_to_passive(engine):
    response = _analyze(engine, "ケーキが食べられる。")
    voices = _voices(response)

    # This surface form can be genuinely ambiguous in isolation. The runtime
    # must not collapse it to passive-only; potential or an explicit ambiguity
    # classification is acceptable until arguments/context resolve the voice.
    assert "potential" in voices or "passive_or_potential" in voices
    assert voices != {"passive"}


def test_rareru_true_passive_is_preserved(engine):
    response = _analyze(engine, "先生に褒められる。")

    assert "passive" in _voices(response) or "passive_or_potential" in _voices(response)


@pytest.mark.parametrize("text", ["雨なので出かけない。", "雨のため試合を中止する。"])
def test_intra_sentence_causal_variants_are_relations(engine, text):
    response = _analyze(engine, text)

    assert "causes" in _relations(response)
