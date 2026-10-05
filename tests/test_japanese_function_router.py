from __future__ import annotations

from deterministic_japanese_parser_mcp.japanese_function_router import (
    ROUTING_VERSION,
    route_japanese_functions,
)
from deterministic_japanese_parser_mcp.models import LexicalCandidate, OriginalSpan, Token


def _token(
    surface: str,
    pos: list[str],
    *,
    status: str = "MATCHED",
    record_id: str | None = None,
    domains: list[str] | None = None,
) -> Token:
    candidates = []
    if record_id:
        candidates.append(
            LexicalCandidate(
                record_id=record_id,
                lemma=surface,
                matched_text=surface,
                match_type="surface",
                domains=domains or [],
            )
        )
    return Token(
        surface=surface,
        normalized=surface,
        reading=None,
        pos=pos,
        span=OriginalSpan(start=0, end=len(surface), source_text=surface),
        lexical_candidates=candidates,
        lexical_candidate_total=len(candidates),
        lexical_status=status,
    )


def test_router_selects_pos_and_projection_lanes_without_resolving_meaning():
    tokens = [
        _token("猫", ["名詞"], record_id="R1", domains=["animals"]),
        _token("走る", ["動詞"], record_id="R2"),
    ]
    trace = route_japanese_functions(
        original_text="猫が走る",
        tokens=tokens,
        record_lanes={
            "R1": ["Noun-Entity", "Usage-Context-Pragmatics"],
            "R2": ["Predicate-Inflection", "Sense-Semantic Relation"],
        },
        projection_version="projection-v1",
        exact_hit_count=2,
    )
    assert trace.routing_version == ROUTING_VERSION
    assert trace.router_decision == "progressive-retrieval"
    assert trace.recovery_needed is False
    assert "Orthography/Reading" in trace.selected_lanes
    assert "Noun-Entity" in trace.selected_lanes
    assert "Predicate-Inflection" in trace.selected_lanes
    assert "Syntax-Case-Clause" in trace.selected_lanes
    assert "Sense-Semantic Relation" in trace.selected_lanes
    assert "Usage-Context-Pragmatics" in trace.selected_lanes
    assert trace.secondary_facets == ["animals"]


def test_router_enters_recovery_for_exact_zero_and_oov():
    tokens = [_token("くだしあ", ["名詞"], status="NO_MATCH")]
    trace = route_japanese_functions(
        original_text="くだしあ",
        tokens=tokens,
        record_lanes={},
        projection_version="projection-v1",
        exact_hit_count=0,
    )
    assert trace.router_decision == "recovery-preparation"
    assert trace.recovery_needed is True
    assert trace.fallback_reason == "exact=0|oov"
    assert "Sense-Semantic Relation" in trace.selected_lanes
    assert "Syntax-Case-Clause" in trace.selected_lanes
    assert "oov" in trace.detected_input_features


def test_router_enters_recovery_for_conflicts_even_with_exact_hits():
    token = _token("確認", ["名詞"], record_id="R1")
    trace = route_japanese_functions(
        original_text="確認",
        tokens=[token],
        record_lanes={"R1": ["Noun-Entity"]},
        projection_version="projection-v1",
        exact_hit_count=1,
        grammar_conflict=True,
        syntax_conflict=True,
    )
    assert trace.recovery_needed is True
    assert trace.fallback_reason == "grammar_conflict|syntax_conflict"
    assert "grammar_conflict" in trace.detected_input_features
    assert "syntax_conflict" in trace.detected_input_features


def test_document_structure_lane_is_selected_only_when_document_evidence_exists():
    token = _token("確認", ["名詞"], record_id="R1")
    single = route_japanese_functions(
        original_text="確認",
        tokens=[token],
        record_lanes={"R1": ["Noun-Entity"]},
        projection_version="projection-v1",
        exact_hit_count=1,
    )
    document = route_japanese_functions(
        original_text="第一段落\n第二段落",
        tokens=[token],
        record_lanes={"R1": ["Noun-Entity"]},
        projection_version="projection-v1",
        exact_hit_count=1,
    )
    assert "Document Structure" not in single.selected_lanes
    assert "Document Structure" in document.selected_lanes


def test_unknown_projection_lane_is_not_promoted():
    token = _token("猫", ["名詞"], record_id="R1")
    trace = route_japanese_functions(
        original_text="猫",
        tokens=[token],
        record_lanes={"R1": ["Noun-Entity", "NOT-A-LANE"]},
        projection_version="projection-v1",
        exact_hit_count=1,
    )
    assert "NOT-A-LANE" not in trace.candidate_lanes
    assert "NOT-A-LANE" not in trace.selected_lanes
