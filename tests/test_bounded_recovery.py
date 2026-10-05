from __future__ import annotations

from deterministic_japanese_parser_mcp.bounded_recovery import (
    RecoveryLimits,
    build_candidate_lattice,
    decide_sentence_recovery,
    generate_local_variants,
    recover_boundary_options,
    recover_token_candidates,
)
from deterministic_japanese_parser_mcp.models import LexicalCandidate, OriginalSpan, Token


class FakeRuntime:
    def __init__(self, surfaces: dict[str, list[str]], readings: dict[str, list[str]] | None = None):
        self.available = True
        self.surfaces = surfaces
        self.readings = readings or {}

    @staticmethod
    def _candidates(text: str, record_ids: list[str], match_type: str):
        return [
            LexicalCandidate(
                record_id=record_id,
                lemma=text,
                matched_text=text,
                match_type=match_type,
            )
            for record_id in record_ids
        ]

    def exact_lookup(self, text: str, *, match_type: str = "surface", max_candidates: int = 8):
        record_ids = self.surfaces.get(text, [])
        return self._candidates(text, record_ids[:max_candidates], match_type), len(record_ids)

    def reading_lookup(self, reading: str, *, surface=None, normalized=None, max_candidates: int = 8):
        record_ids = self.readings.get(reading, [])
        return self._candidates(reading, record_ids[:max_candidates], "reading"), len(record_ids)


def _token(text: str, *, status: str = "NO_MATCH", record_id: str | None = None) -> Token:
    candidates = []
    if record_id:
        candidates = [
            LexicalCandidate(
                record_id=record_id,
                lemma=text,
                matched_text=text,
                match_type="surface",
            )
        ]
    return Token(
        surface=text,
        normalized=text,
        reading=None,
        pos=["unknown"],
        span=OriginalSpan(start=0, end=len(text), source_text=text),
        lexical_candidates=candidates,
        lexical_candidate_total=len(candidates),
        lexical_status=status,
    )


def test_local_variants_are_deterministic_bounded_and_operation_typed():
    limits = RecoveryLimits(max_variants_per_span=5)
    first = generate_local_variants("きゃー", limits=limits)
    second = generate_local_variants("きゃー", limits=limits)

    assert first == second
    assert len(first) <= 5
    assert any(item.operation == "small_kana" for item in first)
    assert any(item.operation == "long_vowel" for item in first)


def test_insertion_and_substitution_are_explicit_policy_inputs_not_hidden_guesses():
    limits = RecoveryLimits(max_variants_per_span=64)
    without_policy = generate_local_variants("か", limits=limits)
    with_policy = generate_local_variants(
        "か",
        limits=limits,
        insertion_alphabet=["な"],
        substitution_alphabet=["き"],
    )

    assert not any(item.operation == "insertion" for item in without_policy)
    assert not any(item.operation == "substitution" for item in without_policy)
    assert any(item.text == "かな" and item.operation == "insertion" for item in with_policy)
    assert any(item.text == "き" and item.operation == "substitution" for item in with_policy)


def test_recovery_promotes_only_candidates_that_land_on_runtime_data():
    runtime = FakeRuntime({"がくせい": ["R-student"]})
    token = _token("かくせい")
    recovered = recover_token_candidates(token, runtime, limits=RecoveryLimits())

    assert [item.candidate_text for item in recovered] == ["がくせい"]
    assert recovered[0].runtime_record_ids == ["R-student"]
    assert recovered[0].evidence_ids == ["runtime:R-student"]
    assert recovered[0].operations == ["dakuten_handakuten"]


def test_known_token_is_not_recovered_without_explicit_force():
    runtime = FakeRuntime({"がくせい": ["R-student"]})
    token = _token("かくせい", status="MATCHED", record_id="R-existing")

    assert recover_token_candidates(token, runtime, limits=RecoveryLimits()) == []


def test_declared_rule_variants_support_okurigana_and_contraction_without_global_fuzzy_scan():
    runtime = FakeRuntime({"行う": ["R-okuri"], "ている": ["R-contract"]})
    limits = RecoveryLimits()
    okuri = recover_token_candidates(
        _token("行なう"),
        runtime,
        limits=limits,
        rule_variants={"行なう": [("行う", "okurigana", 0.5)]},
    )
    contraction = recover_token_candidates(
        _token("てる"),
        runtime,
        limits=limits,
        rule_variants={"てる": [("ている", "contraction", 0.5)]},
    )

    assert okuri[0].operations == ["okurigana"]
    assert contraction[0].operations == ["contraction"]


def test_split_boundary_requires_both_segments_to_land_exactly():
    runtime = FakeRuntime({"東京": ["R-tokyo"], "駅": ["R-station"]})
    token = _token("東京駅")
    options = recover_boundary_options([token], runtime, limits=RecoveryLimits())

    split = [item for item in options[0] if item.operations == ("split",)]
    assert len(split) == 1
    assert split[0].candidate_segments == ("東京", "駅")
    assert split[0].runtime_record_ids == ("R-station", "R-tokyo")


def test_merge_boundary_can_consume_two_tokens_when_combined_surface_lands():
    runtime = FakeRuntime({"取り扱い": ["R-merge"]})
    tokens = [_token("取り"), _token("扱い", status="MATCHED", record_id="R-part")]
    options = recover_boundary_options(tokens, runtime, limits=RecoveryLimits())

    merge = [item for item in options[0] if item.operations == ("merge",)]
    assert len(merge) == 1
    assert merge[0].end_token_exclusive == 2
    assert merge[0].candidate_segments == ("取り扱い",)


def test_sentence_lattice_keeps_unknown_original_path_and_recovered_competitor():
    runtime = FakeRuntime({"学生": ["R-student"]})
    tokens = [_token("学正")]
    recoveries = {
        0: recover_token_candidates(
            tokens[0],
            runtime,
            limits=RecoveryLimits(),
            substitution_alphabet=["生"],
        )
    }
    paths = build_candidate_lattice(tokens, recoveries, limits=RecoveryLimits())

    assert any(path.unresolved_count == 1 and path.text_sequence == ("学正",) for path in paths)
    assert any(path.unresolved_count == 0 and path.text_sequence == ("学生",) for path in paths)


def test_sentence_lattice_supports_split_path_and_whole_sentence_completion():
    runtime = FakeRuntime({"東京": ["R-tokyo"], "駅": ["R-station"], "です": ["R-desu"]})
    tokens = [_token("東京駅"), _token("です", status="MATCHED", record_id="R-desu")]
    boundary = recover_boundary_options(tokens, runtime, limits=RecoveryLimits())
    paths = build_candidate_lattice(
        tokens,
        recoveries={},
        boundary_options=boundary,
        limits=RecoveryLimits(),
    )

    assert any(path.text_sequence == ("東京", "駅", "です") for path in paths)
    assert all(option.end_token_exclusive <= len(tokens) for path in paths for option in path.options)


def test_lattice_budget_fails_closed_instead_of_returning_partial_sentence():
    tokens = [_token("a"), _token("b"), _token("c")]
    limits = RecoveryLimits(max_lattice_nodes=1, top_k_paths=2)
    paths = build_candidate_lattice(tokens, recoveries={}, limits=limits)

    assert paths == []


def test_margin_gate_never_resolves_without_scores_or_with_small_margin():
    token = _token("学正")
    runtime = FakeRuntime({"学生": ["R-student"]})
    limits = RecoveryLimits()
    recoveries = {
        0: recover_token_candidates(
            token,
            runtime,
            limits=limits,
            substitution_alphabet=["生"],
        )
    }
    paths = build_candidate_lattice([token], recoveries, limits=limits)

    no_evidence = decide_sentence_recovery(
        paths,
        path_scores={},
        minimum_score=0.8,
        minimum_margin=0.2,
    )
    assert no_evidence.decision == "INSUFFICIENT"

    recovered_path = next(path for path in paths if path.unresolved_count == 0)
    original_path = next(path for path in paths if path.unresolved_count == 1)
    ambiguous = decide_sentence_recovery(
        paths,
        path_scores={recovered_path.key: 0.90, original_path.key: 0.82},
        minimum_score=0.8,
        minimum_margin=0.2,
    )
    assert ambiguous.decision == "AMBIGUOUS"
    assert ambiguous.selected_path is None


def test_margin_gate_resolves_only_supported_non_unresolved_path():
    token = _token("学正")
    runtime = FakeRuntime({"学生": ["R-student"]})
    limits = RecoveryLimits()
    recoveries = {
        0: recover_token_candidates(
            token,
            runtime,
            limits=limits,
            substitution_alphabet=["生"],
        )
    }
    paths = build_candidate_lattice([token], recoveries, limits=limits)
    recovered_path = next(path for path in paths if path.unresolved_count == 0)
    original_path = next(path for path in paths if path.unresolved_count == 1)

    decision = decide_sentence_recovery(
        paths,
        path_scores={recovered_path.key: 0.95, original_path.key: 0.60},
        minimum_score=0.8,
        minimum_margin=0.2,
    )
    assert decision.decision == "RESOLVED"
    assert decision.selected_path == recovered_path
