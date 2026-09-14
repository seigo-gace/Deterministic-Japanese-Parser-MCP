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


@pytest.mark.parametrize("text", ["まず確認する。", "ずっと待つ。"])
def test_lexical_zu_does_not_create_negation(engine, text):
    response = _analyze(engine, text)

    assert str(response.overall_status) != "OverallStatus.FAILED"
    assert not _scopes(response, "negation")


def test_true_zu_negation_is_preserved(engine):
    response = _analyze(engine, "確認せず進む。")

    assert ("negation", "negation") in _scopes(response)


@pytest.mark.parametrize(
    "text",
    [
        "駅まで歩く。",
        "5時まで働く。",
        "ここでも使える。",
        "水でも飲む。",
    ],
)
def test_nonconditional_made_demo_do_not_create_condition_scope(engine, text):
    response = _analyze(engine, text)

    assert str(response.overall_status) != "OverallStatus.FAILED"
    assert not _scopes(response, "condition")


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
