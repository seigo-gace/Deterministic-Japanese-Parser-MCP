from __future__ import annotations

from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine


def _feature(response, entry_id: str):
    return next(
        item
        for item in response.meaning_graph.language_features
        if item.entry_id == entry_id
    )


def test_slang_polarity_is_resolved_by_local_context() -> None:
    engine = ParserEngine()
    negative = engine.analyze(AnalyzeRequest(
        original_text="このスケジュール、エグい。",
    ))
    positive = engine.analyze(AnalyzeRequest(
        original_text="この完成度、エグい。",
    ))
    assert _feature(negative, "SLANG-EGUI-001").interpretation_id == (
        "egui.negative-extreme"
    )
    assert _feature(positive, "SLANG-EGUI-001").interpretation_id == (
        "egui.positive-extreme"
    )


def test_unqualified_slang_remains_ambiguous() -> None:
    engine = ParserEngine()
    response = engine.analyze(AnalyzeRequest(original_text="エグい。"))
    match = _feature(response, "SLANG-EGUI-001")
    assert match.status.value == "AMBIGUOUS"
    assert set(match.candidate_ids) == {
        "egui.negative-extreme",
        "egui.positive-extreme",
    }
    assert response.overall_status.value == "PARTIAL"
    assert any(
        item["type"] == "language_feature"
        for item in response.meaning_graph.unresolved
    )


def test_onomatopoeia_exposes_sensory_parameters() -> None:
    engine = ParserEngine()
    response = engine.analyze(AnalyzeRequest(
        original_text="表面がざらざらしている。",
    ))
    match = _feature(response, "SENSORY-ZARAZARA-001")
    assert match.parameters["modality"] == "tactile"
    assert match.parameters["roughness"] == 5


def test_modality_level_reaches_same_clause_proposition() -> None:
    engine = ParserEngine()
    response = engine.analyze(AnalyzeRequest(
        original_text="絶対に触るな。",
        execution_mode="external_action",
    ))
    assert _feature(response, "MODALITY-COMMAND-LV5-001").parameters[
        "force_level"
    ] == 5
    assert any(
        item.force_level == 5
        for item in response.meaning_graph.propositions
    )


def test_absolute_adverb_alone_is_not_a_level_five_command() -> None:
    engine = ParserEngine()
    response = engine.analyze(AnalyzeRequest(original_text="絶対に成功する。"))
    ids = {item.entry_id for item in response.meaning_graph.language_features}
    assert "MODALITY-COMMAND-LV5-001" not in ids


def test_honorific_resolution_uses_social_context() -> None:
    engine = ParserEngine()
    response = engine.analyze(AnalyzeRequest(
        original_text="弊社の社長が申しておりました。",
        social_context={
            "speaker_group": "company-a",
            "addressee_group": "company-b",
        },
    ))
    match = _feature(response, "HONORIFIC-MOUSU-001")
    assert match.interpretation_id == "honorific-humble-1.speak"


def test_honorific_without_social_context_fails_closed() -> None:
    engine = ParserEngine()
    response = engine.analyze(AnalyzeRequest(
        original_text="社長が申しておりました。",
        execution_mode="external_action",
    ))
    match = _feature(response, "HONORIFIC-MOUSU-001")
    assert match.status.value == "AMBIGUOUS"
    assert response.execution_allowed is False
    assert "AMBIGUOUS_LANGUAGE_FEATURE" in response.blocked_reasons


def test_longest_sentence_final_particle_wins() -> None:
    engine = ParserEngine()
    response = engine.analyze(AnalyzeRequest(original_text="いいよね。"))
    ids = {
        item.entry_id for item in response.meaning_graph.language_features
    }
    assert "PARTICLE-YONE-001" in ids
    assert "PARTICLE-NE-001" not in ids
    assert "PARTICLE-YO-001" not in ids


def test_backchannel_exact_match_allows_terminal_punctuation() -> None:
    engine = ParserEngine()
    response = engine.analyze(AnalyzeRequest(original_text="はい。"))
    assert _feature(response, "BACKCHANNEL-HAI-001").status.value == "RESOLVED"


def test_sentence_final_particle_does_not_match_inside_verb() -> None:
    engine = ParserEngine()
    response = engine.analyze(AnalyzeRequest(original_text="死ね。"))
    ids = {item.entry_id for item in response.meaning_graph.language_features}
    assert "PARTICLE-NE-001" not in ids
