from __future__ import annotations

from collections.abc import Mapping
from typing import Iterable

from .interpretation_contracts import (
    JAPANESE_FUNCTION_LANES,
    JapaneseFunctionLane,
    RouterLaneSkip,
    RouterRetrievalLimits,
    RouterTrace,
)
from .models import Token


ROUTING_VERSION = "japanese-function-router-v1"

_NOUN_MARKERS = ("名詞", "代名詞", "noun", "pronoun", "proper noun")
_PREDICATE_MARKERS = ("動詞", "形容詞", "形状詞", "verb", "adjective", "adjectival")
_FUNCTION_MARKERS = ("助詞", "助動詞", "particle", "auxiliary")
_CONNECTIVE_MARKERS = ("接続詞", "副詞", "連体詞", "conjunction", "adverb", "prenominal")


def _has_pos(token: Token, markers: tuple[str, ...]) -> bool:
    text = " ".join(token.pos).casefold()
    return any(marker.casefold() in text for marker in markers)


def _ordered_lanes(values: Iterable[str]) -> list[JapaneseFunctionLane]:
    selected = set(values)
    return [lane for lane in JAPANESE_FUNCTION_LANES if lane in selected]


def route_japanese_functions(
    *,
    original_text: str,
    tokens: list[Token],
    record_lanes: Mapping[str, Iterable[str]],
    projection_version: str,
    exact_hit_count: int,
    segmentation_suspicious: bool = False,
    grammar_conflict: bool = False,
    syntax_conflict: bool = False,
    limits: RouterRetrievalLimits | None = None,
) -> RouterTrace:
    """Select evidence lanes without resolving lexical or sentence meaning.

    `record_lanes` is supplied by the projection layer for already discovered
    lexical candidates.  The router may broaden the evidence lanes, but it
    never chooses a lexical sense or creates meaning from a lane label.
    """
    if limits is None:
        limits = RouterRetrievalLimits(
            max_candidates_per_lane=32,
            max_total_candidates=128,
            max_recovery_passes=2,
            max_work_ms=25.0,
        )

    features: set[str] = set()
    candidates: set[str] = {"Orthography/Reading"}
    selected: set[str] = {"Orthography/Reading"}
    secondary_facets: set[str] = set()

    if any(_has_pos(token, _NOUN_MARKERS) for token in tokens):
        features.add("noun_or_entity_candidate")
        candidates.add("Noun-Entity")
        selected.add("Noun-Entity")
    if any(_has_pos(token, _PREDICATE_MARKERS) for token in tokens):
        features.add("predicate_or_inflection_candidate")
        candidates.add("Predicate-Inflection")
        selected.add("Predicate-Inflection")
    if any(_has_pos(token, _FUNCTION_MARKERS) for token in tokens):
        features.add("function_word_candidate")
        candidates.add("Function Words")
        selected.add("Function Words")
    if any(_has_pos(token, _CONNECTIVE_MARKERS) for token in tokens):
        features.add("connective_or_modifier_candidate")
        candidates.add("Connective-Modifier")
        selected.add("Connective-Modifier")
    if len(tokens) > 1:
        features.add("multi_token_input")
        candidates.add("Syntax-Case-Clause")
        selected.add("Syntax-Case-Clause")
    if "\n" in original_text:
        features.add("document_structure_present")
        candidates.add("Document Structure")
        selected.add("Document Structure")

    oov_count = sum(1 for token in tokens if token.lexical_status == "NO_MATCH")
    ambiguous_count = sum(1 for token in tokens if token.lexical_status == "AMBIGUOUS")
    if oov_count:
        features.add("oov")
    if ambiguous_count:
        features.add("lexical_ambiguity")

    for token in tokens:
        for lexical in token.lexical_candidates:
            secondary_facets.update(value for value in lexical.domains if value)
            for lane in record_lanes.get(lexical.record_id, ()):
                if lane in JAPANESE_FUNCTION_LANES:
                    candidates.add(lane)
                    # Projection membership is evidence that the lane can help,
                    # not that the candidate is semantically correct.
                    selected.add(lane)

    fallback_reasons: list[str] = []
    if exact_hit_count <= 0:
        fallback_reasons.append("exact=0")
    if oov_count:
        fallback_reasons.append("oov")
    if segmentation_suspicious:
        fallback_reasons.append("suspicious_segmentation")
        features.add("suspicious_segmentation")
    if grammar_conflict:
        fallback_reasons.append("grammar_conflict")
        features.add("grammar_conflict")
    if syntax_conflict:
        fallback_reasons.append("syntax_conflict")
        features.add("syntax_conflict")

    recovery_needed = bool(fallback_reasons)
    if recovery_needed:
        # Recovery needs lexical/sense/syntax evidence available for bounded
        # re-evaluation, but these lanes still do not become meaning authority.
        candidates.update(
            {
                "Orthography/Reading",
                "Sense-Semantic Relation",
                "Syntax-Case-Clause",
            }
        )
        selected.update(
            {
                "Orthography/Reading",
                "Sense-Semantic Relation",
                "Syntax-Case-Clause",
            }
        )

    candidate_lanes = _ordered_lanes(candidates)
    selected_lanes = _ordered_lanes(selected)
    skipped = [
        RouterLaneSkip(lane=lane, reason="no_current_input_or_projection_evidence")
        for lane in JAPANESE_FUNCTION_LANES
        if lane not in selected
    ]
    decision = "recovery-preparation" if recovery_needed else "progressive-retrieval"
    return RouterTrace(
        detected_input_features=sorted(features),
        router_decision=decision,
        candidate_lanes=candidate_lanes,
        selected_lanes=selected_lanes,
        skipped_lanes=skipped,
        secondary_facets=sorted(secondary_facets),
        fallback_reason="|".join(fallback_reasons) if fallback_reasons else None,
        recovery_needed=recovery_needed,
        routing_version=ROUTING_VERSION,
        projection_version=projection_version,
        retrieval_limits=limits,
    )
