from __future__ import annotations

import hashlib
import re
from typing import Iterable

from .models import (
    ItemStatus,
    LexicalCandidate,
    LexicalNode,
    MeaningGraph,
    OriginalSpan,
    Proposition,
    Token,
)


_POS_FAMILY_MARKERS: dict[str, tuple[str, ...]] = {
    "名詞": ("noun", "pronoun", "counter", "prefix", "suffix"),
    "動詞": ("verb",),
    "形容詞": ("adjective",),
    "形状詞": ("adjectival", "adjective"),
    "副詞": ("adverb",),
    "助詞": ("particle",),
    "助動詞": ("auxiliary",),
    "接続詞": ("conjunction",),
    "感動詞": ("interjection",),
    "連体詞": ("prenominal", "pre-noun"),
}

# These cues are deliberately small, project-authored and deterministic. They
# do not import or approve the separate 5,000 context-candidate collection.
_DOMAIN_CONTEXT_CUES: dict[str, tuple[str, ...]] = {
    "computing": (
        "API",
        "UI",
        "GitHub",
        "Notion",
        "MCP",
        "DB",
        "JSON",
        "YAML",
        "コード",
        "サーバー",
        "アプリ",
        "リポジトリ",
        "ブランチ",
    ),
    "business": ("事業", "顧客", "売上", "料金", "契約", "請求"),
    "economics": ("経済", "市場", "価格", "需要", "供給"),
    "finance": ("金融", "投資", "株式", "資金", "決済"),
    "law": ("法律", "規約", "条項", "契約", "権利", "義務"),
    "medicine": ("医療", "病院", "診断", "症状", "治療"),
    "biology": ("生物", "細胞", "遺伝子", "生態"),
    "chemistry": ("化学", "分子", "元素", "反応"),
    "physics": ("物理", "量子", "力学", "電磁"),
    "mathematics": ("数学", "数式", "関数", "確率", "統計"),
    "linguistics": ("言語", "文法", "語彙", "構文", "意味"),
    "shogi": ("将棋", "棋士", "駒", "王手"),
    "sports": ("競技", "試合", "選手", "得点"),
}

_KANJI = re.compile(r"[一-龥々〆ヵヶ]")
_KANA_ONLY = re.compile(r"^[ぁ-ゖァ-ヺー]+$")


def _katakana_to_hiragana(value: str) -> str:
    return "".join(
        chr(ord(char) - 0x60) if "ァ" <= char <= "ヶ" else char
        for char in value
    )


def _overlap(left: OriginalSpan, right: OriginalSpan) -> bool:
    return left.start < right.end and right.start < left.end


def _stable_hash(graph: MeaningGraph) -> str:
    return hashlib.sha256(
        graph.model_dump_json(exclude={"semantic_hash"}).encode("utf-8")
    ).hexdigest()


def _candidate_pos_matches(token: Token, candidate: LexicalCandidate) -> bool:
    candidate_pos = " ".join(candidate.part_of_speech).lower()
    for token_pos in token.pos:
        markers = _POS_FAMILY_MARKERS.get(token_pos, ())
        if any(marker in candidate_pos for marker in markers):
            return True
    return False


def _related_propositions(
    token: Token,
    propositions: Iterable[Proposition],
) -> list[Proposition]:
    direct: list[Proposition] = []
    same_clause: list[Proposition] = []
    for proposition in propositions:
        argument_overlap = any(
            argument.span is not None and _overlap(token.span, argument.span)
            for argument in proposition.arguments
        )
        if _overlap(token.span, proposition.source_span) or argument_overlap:
            direct.append(proposition)
        elif (
            proposition.clause_id
            and proposition.source_span.start <= token.span.start
            and token.span.end <= proposition.source_span.end
        ):
            same_clause.append(proposition)
    return direct or same_clause


class LexicalGraphEnricher:
    """Connect exact open-lexicon candidates to MeaningGraph nodes.

    This layer resolves lexical identity only. It does not invent dictionary
    senses and never changes proposition intent, task generation, pragmatic
    meaning, or external-action eligibility.
    """

    def __init__(self, *, max_nodes: int = 256) -> None:
        self.max_nodes = max(1, max_nodes)
        self.last_metrics: dict[str, int | float | str] = {}

    @staticmethod
    def _score_candidate(
        token: Token,
        candidate: LexicalCandidate,
        context_text: str,
    ) -> tuple[int, list[str]]:
        score = 0
        evidence: list[str] = []

        if candidate.match_type == "surface":
            score += 100
            evidence.append("surface_exact")
        elif candidate.match_type == "normalized":
            score += 75
            evidence.append("normalized_exact")
        else:
            score += 50
            evidence.append("reading_lookup")

        token_reading = _katakana_to_hiragana(token.reading or "")
        candidate_readings = {
            _katakana_to_hiragana(value)
            for value in candidate.readings
            if value
        }
        if token_reading and token_reading in candidate_readings:
            score += 30
            evidence.append("token_reading_match")

        if _candidate_pos_matches(token, candidate):
            score += 20
            evidence.append("token_pos_family_match")

        if candidate.restricted_to and (
            token.surface in candidate.restricted_to
            or token.normalized in candidate.restricted_to
        ):
            score += 10
            evidence.append("reading_restriction_match")

        if candidate.no_kanji and not _KANJI.search(token.surface):
            score += 5
            evidence.append("no_kanji_compatible")

        if _KANA_ONLY.fullmatch(token.surface or "") and any(
            "usually written using kana alone" in label.lower()
            for label in candidate.usage_labels
        ):
            score += 5
            evidence.append("kana_usage_match")

        folded_context = context_text.casefold()
        for domain in candidate.domains:
            cues = _DOMAIN_CONTEXT_CUES.get(domain.casefold(), ())
            matched = [cue for cue in cues if cue.casefold() in folded_context]
            if matched:
                score += 25
                evidence.append(f"domain_context:{domain}:{matched[0]}")
                break

        if (
            candidate.source_dataset
            and candidate.source_version
            and candidate.source_license
        ):
            score += 1
            evidence.append("source_provenance_complete")

        return score, evidence

    @staticmethod
    def _select(
        token: Token,
        ranked: list[tuple[int, LexicalCandidate, list[str]]],
    ) -> tuple[str | None, str, float]:
        if not ranked:
            return None, "no_candidates", 0.0
        if token.lexical_candidate_total > len(ranked):
            return None, "candidate_list_truncated", 0.0
        if token.lexical_candidate_total == 1:
            return ranked[0][1].record_id, "single_candidate", 1.0

        top_score, top_candidate, top_evidence = ranked[0]
        second_score = ranked[1][0] if len(ranked) > 1 else 0
        margin = top_score - second_score
        substantive = [
            item
            for item in top_evidence
            if item != "source_provenance_complete"
        ]
        if top_score >= 120 and margin >= 25 and len(substantive) >= 2:
            confidence = min(0.99, 0.60 + margin / 100)
            return (
                top_candidate.record_id,
                "deterministic_context_margin",
                round(confidence, 4),
            )
        return None, "insufficient_context_margin", 0.0

    def enrich(
        self,
        graph: MeaningGraph,
        *,
        tokens: list[Token],
        original_text: str,
        conversation_context: list[str],
        known_entities: list[str],
    ) -> MeaningGraph:
        context_text = "\n".join([
            original_text,
            *conversation_context,
            *known_entities,
        ])
        lexical_nodes: list[LexicalNode] = []
        resolved = 0
        ambiguous = 0
        candidate_count = 0
        truncated_nodes = 0

        for token in tokens:
            if not token.lexical_candidates:
                continue
            if len(lexical_nodes) >= self.max_nodes:
                truncated_nodes += 1
                continue

            ranked = []
            for candidate in token.lexical_candidates:
                score, evidence = self._score_candidate(
                    token,
                    candidate,
                    context_text,
                )
                ranked.append((score, candidate, evidence))
            ranked.sort(
                key=lambda item: (-item[0], item[1].record_id)
            )
            selected_record_id, reason, confidence = self._select(token, ranked)
            status = (
                ItemStatus.RESOLVED
                if selected_record_id
                else ItemStatus.AMBIGUOUS
            )
            if selected_record_id:
                resolved += 1
            else:
                ambiguous += 1
            candidate_count += token.lexical_candidate_total

            related = _related_propositions(token, graph.propositions)
            related_entity_ids = list(dict.fromkeys(
                argument.entity_id
                for proposition in related
                for argument in proposition.arguments
                if argument.entity_id
            ))
            related_sense_ids = list(dict.fromkeys(
                proposition.sense_id
                for proposition in related
                if proposition.sense_id
            ))
            lexical_nodes.append(LexicalNode(
                lexical_node_id=f"L-{len(lexical_nodes) + 1:03d}",
                surface=token.surface,
                normalized=token.normalized,
                reading=token.reading,
                pos=list(token.pos),
                source_span=token.span,
                candidates=[item[1] for item in ranked],
                candidate_scores={
                    item[1].record_id: item[0] for item in ranked
                },
                candidate_evidence={
                    item[1].record_id: item[2] for item in ranked
                },
                selected_record_id=selected_record_id,
                resolution_reason=reason,
                resolution_confidence=confidence,
                related_proposition_ids=[
                    item.proposition_id for item in related
                ],
                related_entity_ids=related_entity_ids,
                related_sense_ids=related_sense_ids,
                status=status,
            ))

        quality = {
            **graph.quality_annotations,
            "lexical_graph_version": "1.0.0",
            "lexical_resolution_policy": (
                "surface-reading-pos-reviewed-domain-cues-v1"
            ),
            "lexical_node_count": len(lexical_nodes),
            "resolved_lexical_nodes": resolved,
            "ambiguous_lexical_nodes": ambiguous,
            "lexical_candidate_count": candidate_count,
            "lexical_node_limit_skips": truncated_nodes,
            "context_candidate_registry_used": False,
            "semantic_auto_promotion": False,
            "intent_auto_promotion": False,
            "task_auto_promotion": False,
            "external_action_auto_promotion": False,
        }
        updated = graph.model_copy(update={
            "lexical_nodes": lexical_nodes,
            "quality_annotations": quality,
        })
        updated = updated.model_copy(update={
            "semantic_hash": _stable_hash(updated)
        })
        self.last_metrics = {
            "lexical_node_count": len(lexical_nodes),
            "resolved_lexical_node_count": resolved,
            "ambiguous_lexical_node_count": ambiguous,
            "lexical_candidate_count": candidate_count,
            "lexical_node_limit_skip_count": truncated_nodes,
            "lexical_context_registry_used": 0,
        }
        return updated
