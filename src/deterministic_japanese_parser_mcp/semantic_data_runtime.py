from __future__ import annotations

from collections import OrderedDict
import gzip
import hashlib
import json
from pathlib import Path
import re
from tempfile import TemporaryFile
from threading import Lock
from typing import Any, BinaryIO, Iterable
import unicodedata

from .grammar_kernel import ACTION_INTENTS, CONSTRAINT_INTENTS
from .models import (
    ItemStatus,
    LanguageFeatureMatch,
    MeaningGraph,
    OriginalSpan,
    Proposition,
    SenseCandidate,
    SocialContext,
    Token,
)


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    return re.sub(r"\s+", "", value).casefold()


def _load_json_gzip(path: Path) -> Any:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def _overlap(left: OriginalSpan, right: OriginalSpan) -> bool:
    return left.start < right.end and right.start < left.end


def _stable_hash(graph: MeaningGraph) -> str:
    return hashlib.sha256(
        graph.model_dump_json(exclude={"semantic_hash"}).encode("utf-8")
    ).hexdigest()


def _contains_all(text: str, values: Iterable[str]) -> bool:
    folded = text.casefold()
    return all(str(value).casefold() in folded for value in values if str(value))


def _contains_any(text: str, values: Iterable[str]) -> bool:
    folded = text.casefold()
    return any(str(value).casefold() in folded for value in values if str(value))


def _structured_markers(value: Any, *, prefix: str = "") -> set[str]:
    """Flatten caller-supplied context into exact, normalized markers."""

    markers: set[str] = set()
    if isinstance(value, dict):
        for key in sorted(value):
            child_prefix = f"{prefix}:{key}" if prefix else str(key)
            markers.update(_structured_markers(value[key], prefix=child_prefix))
        return markers
    if isinstance(value, (list, tuple, set)):
        for item in value:
            markers.update(_structured_markers(item, prefix=prefix))
        return markers
    if value is None or value is False:
        return markers
    if value is True:
        if prefix:
            markers.add(_normalize(prefix))
        return markers

    marker = _normalize(str(value))
    if marker:
        markers.add(marker)
        if prefix:
            markers.add(_normalize(f"{prefix}:{value}"))
    return markers


def _social_markers(social_context: SocialContext | None) -> set[str]:
    if social_context is None:
        return set()
    return _structured_markers(social_context.model_dump(mode="json"))


def _discourse_markers(
    graph: MeaningGraph,
    discourse_state: dict[str, Any] | None,
) -> set[str]:
    markers = _structured_markers(discourse_state or {})
    reading = graph.reading_analysis
    for operator in reading.scope_operators:
        markers.update({
            _normalize(operator.operator_type),
            _normalize(f"scope:{operator.operator_type}"),
            _normalize(f"scope:{operator.semantic_value}"),
        })
    for frame in reading.attribution_frames:
        markers.update({
            _normalize(frame.attribution_type),
            _normalize(f"attribution:{frame.attribution_type}"),
        })
    for relation in reading.discourse_relations:
        markers.update({
            _normalize(relation.relation),
            _normalize(f"discourse:{relation.relation}"),
        })
    return {marker for marker in markers if marker}


def _has_required_markers(
    required: Iterable[str],
    available: set[str],
) -> bool:
    normalized = {_normalize(str(value)) for value in required if str(value)}
    return normalized.issubset(available)


_FUNCTION_WORD_POS_HEADS = frozenset({
    "助詞",
    "助動詞",
    "記号",
    "補助記号",
    "接続詞",
    "フィラー",
})


def _is_function_word_token(token: Token) -> bool:
    if not token.pos:
        return False
    head = token.pos[0]
    if head in _FUNCTION_WORD_POS_HEADS:
        return True
    joined = "-".join(token.pos)
    return any(
        joined == value or joined.startswith(f"{value}-")
        for value in _FUNCTION_WORD_POS_HEADS
    )


def _candidate_context_texts(
    record: dict[str, Any],
    candidate: dict[str, Any],
) -> list[str]:
    texts: list[str] = []
    label = candidate.get("label")
    if label:
        texts.append(str(label))
    for gloss in candidate.get("glosses") or []:
        if gloss:
            texts.append(str(gloss))
    examples = record.get("examples")
    if isinstance(examples, dict):
        for item in examples.get("positive") or []:
            if item:
                texts.append(str(item))
    elif isinstance(examples, list):
        for item in examples:
            if item:
                texts.append(str(item))
    return texts


def _record_lookup_definition_texts(record: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for candidate in record.get("meaning_candidates", []):
        if candidate.get("review_status") != "approved":
            continue
        label = candidate.get("label")
        if label:
            texts.append(str(label))
        for gloss in candidate.get("glosses") or []:
            if gloss:
                texts.append(str(gloss))
    for key in (
        "positive_examples",
        "negative_examples",
        "boundary_examples",
    ):
        for item in record.get(key) or []:
            if item:
                texts.append(str(item))
    examples = record.get("examples")
    if isinstance(examples, dict):
        for item in examples.get("positive") or []:
            if item:
                texts.append(str(item))
    elif isinstance(examples, list):
        for item in examples:
            if item:
                texts.append(str(item))
    return texts


_JP_OVERLAP_SEGMENT_RE = re.compile(
    r"[\u4E00-\u9FFF\u30A0-\u30FF]{2,}|[\u3040-\u309F]{2,}"
)
_KANJI_RUN_RE = re.compile(r"[\u4E00-\u9FFF]{2,}")

_CASE_MARKED_PARTICLE_SURFACES = frozenset({"を", "へ", "で"})
_CASE_BUFFER_RESET_SURFACES = frozenset({"が", "は", "も", "の", "と", "から", "まで", "より"})

_OVERLAP_STOP_SEGMENTS = frozenset({
    _normalize(value)
    for value in (
        "する",
        "ある",
        "ない",
        "こと",
        "もの",
        "ため",
        "など",
        "において",
        "における",
        "という",
        "といった",
        "として",
        "から",
        "まで",
        "などの",
        "るための",
        "くなっている",
        "比較的高",
    )
})


def _japanese_overlap_segments(text: str) -> set[str]:
    return {
        _normalize(match.group(0))
        for match in _JP_OVERLAP_SEGMENT_RE.finditer(text or "")
    }


def _meaningful_overlap_segments(text: str, *, excluded: set[str]) -> set[str]:
    return {
        segment
        for segment in _japanese_overlap_segments(text)
        if segment not in excluded
        and segment not in _OVERLAP_STOP_SEGMENTS
    }


def _salient_kanji_overlap_score(
    context_texts: Iterable[str],
    neighbor_definitions: str,
    *,
    excluded: set[str],
) -> int:
    if not neighbor_definitions.strip():
        return 0
    neighbor_runs = _KANJI_RUN_RE.findall(neighbor_definitions)
    if not neighbor_runs:
        return 0
    neighbor_kanji = set("".join(neighbor_runs))
    score = 0
    for text in context_texts or []:
        gloss_runs = _KANJI_RUN_RE.findall(str(text))
        if not gloss_runs:
            continue
        gloss_kanji = set("".join(gloss_runs))
        gloss_kanji -= {
            char
            for char in gloss_kanji
            if _normalize(char) in excluded
        }
        shared = gloss_kanji & neighbor_kanji
        if not shared:
            continue
        meaningful = set()
        for run in neighbor_runs:
            if any(char in shared for char in run):
                meaningful.update(char for char in run if char in shared)
        if meaningful:
            score += min(len(meaningful), 4) * 10
    return score


def _case_marked_argument_tokens(tokens: list[Token]) -> list[Token]:
    marked: list[Token] = []
    buffer: list[Token] = []
    for token in tokens:
        if _is_function_word_token(token):
            if token.surface in _CASE_MARKED_PARTICLE_SURFACES and buffer:
                marked.extend(buffer)
                buffer = []
            elif token.surface in _CASE_BUFFER_RESET_SURFACES:
                buffer = []
            continue
        buffer.append(token)
    return marked


def _destination_tokens_for_verb(tokens: list[Token]) -> list[Token]:
    marked_starts = {
        token.span.start for token in _case_marked_argument_tokens(tokens)
    }
    destinations: list[Token] = []
    for index, token in enumerate(tokens):
        if token.surface != "へ" or index == 0:
            continue
        previous = tokens[index - 1]
        if previous.span.start in marked_starts:
            destinations.append(previous)
    return destinations


def _marked_case_phrase_surfaces(tokens: list[Token]) -> dict[str, str]:
    phrases: dict[str, str] = {}
    buffer: list[str] = []
    for token in tokens:
        if token.surface in {"が", "を"} and buffer:
            phrases[token.surface] = "".join(buffer)
            buffer = []
            continue
        if token.surface in _CASE_BUFFER_RESET_SURFACES:
            buffer = []
            continue
        if _is_function_word_token(token):
            continue
        buffer.append(token.surface)
    return phrases


def _clause_surface(tokens: list[Token]) -> str:
    return "".join(token.surface for token in tokens)


def _collocate_sense_adjustment(
    candidate: dict[str, Any],
    *,
    token: Token,
    tokens: list[Token],
    neighbor_definitions: str,
) -> tuple[int, list[str]]:
    label = str(candidate.get("label") or "")
    if not label:
        return 0, []
    neighbor_norm = _normalize(neighbor_definitions)
    lemma = _normalize(token.normalized or token.surface)
    effective_lemma = lemma
    if any("サ変" in part for part in (token.pos or [])):
        for other in tokens:
            if other.span.start <= token.span.start:
                continue
            if _normalize(other.normalized or other.surface) in {
                _SURU_LIGHT_VERB,
                _normalize("為る"),
            }:
                effective_lemma = _normalize(f"{token.normalized or token.surface}する")
                break
    score = 0
    evidence: list[str] = []

    if "漢字表記" in label and (
        neighbor_definitions.strip() or _destination_tokens_for_verb(tokens)
    ):
        score -= 40
        evidence.append("semantic_pack_kana_notation_demotion")

    destinations = _destination_tokens_for_verb(tokens)
    if destinations and all(
        "固有名詞" in (item.pos or []) for item in destinations
    ):
        if any(
            marker in label
            for marker in (
                "ミーティング",
                "礼拝",
                "大学",
                "出席",
                "ゲーム",
            )
        ):
            score -= 35
            evidence.append("semantic_pack_destination_place_demotion")
        elif any(
            marker in label
            for marker in ("目的地", "移動", "旅", "向か", "着く", "進む")
        ):
            score += 25
            evidence.append("semantic_pack_destination_locomotion_boost")

    if lemma and lemma in neighbor_norm:
        if any(
            marker in label
            for marker in ("地域", "期間", "カバー", "広がる", "転々", "旅行")
        ):
            score -= 30
            evidence.append("semantic_pack_object_verb_purpose_demotion")
        elif any(
            marker in label
            for marker in ("横切", "通り越", "突き抜", "構築", "横断")
        ):
            score += 25
            evidence.append("semantic_pack_object_verb_purpose_boost")

    if "のみ" in label and any(
        marker in neighbor_definitions
        for marker in ("食用", "食物", "摂取", "食事")
    ):
        score -= 45
        evidence.append("semantic_pack_food_collocate_restriction_demotion")
    elif any(
        marker in label for marker in ("食物", "摂取", "固形食物", "食事")
    ) and any(
        marker in neighbor_definitions
        for marker in ("食用", "食物", "摂取", "食事")
    ):
        score += 30
        evidence.append("semantic_pack_food_collocate_ingestion_boost")

    case_phrases = _marked_case_phrase_surfaces(tokens)
    object_phrase = case_phrases.get("を", "")
    agent_phrase = case_phrases.get("が", "")
    collocate_text = "\n".join(
        part for part in (object_phrase, agent_phrase, neighbor_definitions) if part
    )
    clause_text = _clause_surface(tokens)

    polite_request = "ください" in clause_text or "下さい" in clause_text

    if effective_lemma == _normalize("読む") or token.normalized == "読む":
        printed_object = any(
            marker in object_phrase
            for marker in ("本", "書", "紙", "新聞", "雑誌", "記事")
        )
        printed_definition = any(
            marker in collocate_text
            for marker in ("印刷", "書かれ", "読み物", "ページ", "文字")
        )
        if printed_object or printed_definition:
            if any(
                marker in label
                for marker in ("印象", "意味を伝", "伝える", "示す")
            ):
                score -= 35
                evidence.append("semantic_pack_read_printed_matter_demotion")
            elif any(
                marker in label
                for marker in ("読", "書", "文字", "ページ", "文")
            ):
                score += 30
                evidence.append("semantic_pack_read_printed_matter_boost")

    if effective_lemma == _normalize("降る") or token.normalized == "降る":
        weather_agent = any(
            marker in agent_phrase for marker in ("雨", "雪", "雹", "みぞれ")
        )
        weather_definition = any(
            marker in collocate_text
            for marker in ("降水", "天候", "気象", "雲")
        )
        if weather_agent or weather_definition:
            if any(
                marker in label
                for marker in ("重力", "落下", "歯止め", "地に落")
            ):
                score -= 35
                evidence.append("semantic_pack_precipitation_fall_demotion")
            elif any(
                marker in label
                for marker in ("降水", "雨", "雪", "雲", "天候")
            ):
                score += 30
                evidence.append("semantic_pack_precipitation_boost")

    if effective_lemma == _normalize("来る") or token.normalized == "来る":
        person_agent = bool(
            agent_phrase
            and (
                agent_phrase.endswith(("さん", "様", "君", "ちゃん"))
                or any(
                    marker in collocate_text
                    for marker in ("人", "氏", "訪問", "来客")
                )
            )
        )
        if person_agent:
            if any(
                marker in label
                for marker in ("存在", "起きる", "ある一連")
            ):
                score -= 35
                evidence.append("semantic_pack_arrival_existence_demotion")
            elif any(
                marker in label
                for marker in ("来訪", "到着", "訪", "やって来", "来た")
            ):
                score += 30
                evidence.append("semantic_pack_arrival_boost")

    if effective_lemma in {_normalize("やめる"), _normalize("止める")} or token.normalized in {
        "やめる",
        "止める",
    }:
        if polite_request:
            if any(marker in label for marker in ("痛む", "古語", "方言")):
                score -= 40
                evidence.append("semantic_pack_polite_stop_pain_demotion")
            elif any(
                marker in label
                for marker in ("中止", "停止", "やめ", "辞め", "止め")
            ):
                score += 30
                evidence.append("semantic_pack_polite_stop_boost")

    if effective_lemma == _normalize("行く") or token.normalized == "行く":
        if "ないで" in clause_text and polite_request:
            if any(marker in label for marker in ("形勢", "動作について")):
                score -= 35
                evidence.append("semantic_pack_go_prohibition_demotion")
            elif any(
                marker in label
                for marker in ("移動", "向か", "行き", "赴", "出向")
            ):
                score += 25
                evidence.append("semantic_pack_go_motion_boost")

    if effective_lemma == _normalize("中止する") or token.normalized in {
        "中止",
        "中止する",
    }:
        conditional_clause = "なら" in clause_text or "もし" in clause_text
        if conditional_clause:
            if any(
                marker in label
                for marker in ("国文法", "述語用言", "連用形", "区切")
            ):
                score -= 55
                evidence.append("semantic_pack_conditional_cancel_grammar_demotion")
            elif any(
                marker in label
                for marker in (
                    "中止",
                    "取消",
                    "キャンセル",
                    "止める",
                    "中断",
                    "とりやめ",
                    "予定",
                )
            ):
                score += 45
                evidence.append("semantic_pack_conditional_cancel_boost")

    if effective_lemma in {_normalize("開く"), _normalize("開ける")} or token.normalized in {
        "開く",
        "開ける",
    }:
        physical_object = any(
            marker in object_phrase
            for marker in ("ドア", "扉", "戸", "窓", "蓋", "栓")
        )
        if physical_object or object_phrase:
            if any(
                marker in label
                for marker in ("成長", "進化", "展開", "分化", "進歩")
            ):
                score -= 40
                evidence.append("semantic_pack_open_physical_demotion")
            elif any(
                marker in label
                for marker in ("開", "閉", "戸", "扉", "解錠")
            ):
                score += 25
                evidence.append("semantic_pack_open_physical_boost")

    return score, evidence


def _case_linked_neighbor_definitions(
    tokens: list[Token],
    *,
    current: Token,
    neighbor_definition_by_span_start: dict[int, str],
) -> str:
    parts: list[str] = []
    seen_starts: set[int] = set()
    for argument_token in _case_marked_argument_tokens(tokens):
        span_start = argument_token.span.start
        if span_start == current.span.start or span_start in seen_starts:
            continue
        seen_starts.add(span_start)
        definition = neighbor_definition_by_span_start.get(span_start)
        if definition:
            parts.append(definition)
    if parts:
        return "\n".join(parts)
    return "\n".join(
        text
        for span_start, text in neighbor_definition_by_span_start.items()
        if span_start != current.span.start
    )


def _neighbor_definition_overlap_bonus(
    context_texts: Iterable[str],
    neighbor_definitions: str,
    *,
    token: Token,
) -> tuple[int, bool]:
    excluded = {
        _normalize(token.surface),
        _normalize(token.normalized),
    }
    excluded = {value for value in excluded if value}
    candidate_segments: set[str] = set()
    for text in context_texts:
        candidate_segments.update(
            _meaningful_overlap_segments(text, excluded=excluded)
        )
    neighbor_segments = _meaningful_overlap_segments(
        neighbor_definitions,
        excluded=excluded,
    )
    overlap_kinds = candidate_segments.intersection(neighbor_segments)
    bonus = min(len(overlap_kinds), 3) * 15
    bonus += _salient_kanji_overlap_score(
        context_texts,
        neighbor_definitions,
        excluded=excluded,
    )
    if bonus <= 0:
        return 0, False
    return bonus, True


def _inference_sources_profile_locked(sources: Iterable[str] | None) -> bool:
    for source in sources or []:
        if source.startswith("sense_profile:") or source.startswith(
            "sense_ambiguous:"
        ):
            return True
    return False


_JAPANESE_SCRIPT_RE = re.compile(
    r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]"
)
_KATAKANA_RE = re.compile(r"^[\u30A0-\u30FFー]+$")
_KANJI_RE = re.compile(r"[\u4E00-\u9FFF]")

_SUDACHI_POS_CANONICAL: dict[str, frozenset[str]] = {
    "名詞": frozenset({"noun", "n", "名詞", "普通名詞", "一般", "普通名詞-一般"}),
    "動詞": frozenset({"verb", "v", "動詞"}),
    "形容詞": frozenset({"adj", "adjective", "a", "形容詞"}),
    "副詞": frozenset({"adv", "adverb", "副詞"}),
}

_POS_BOOST_BLOCK_VALUES = frozenset({
    _normalize("proper-name"),
    _normalize("unclassified name"),
})

_EVERYDAY_SENSE_MARKERS = ("通常", "一般", "愛玩")

_SURU_LIGHT_VERB = _normalize("する")

_WEATHER_SURFACE = _normalize("天気")
_WEATHER_LABEL_MARKERS = ("天候", "空", "気象", "大気", "降水", "晴れ")
_WEATHER_NON_METEOROLOGY_MARKERS = ("機嫌", "皇帝", "天皇", "主君")


def _has_japanese_script(text: str) -> bool:
    return bool(_JAPANESE_SCRIPT_RE.search(text or ""))


def _label_core(label: str) -> str:
    value = unicodedata.normalize("NFKC", label or "")
    value = re.sub(
        r"[^\w\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]",
        "",
        value,
    )
    return value.casefold()


def _is_distinct_japanese_word_core(core: str) -> bool:
    if len(core) < 2:
        return False
    if _KATAKANA_RE.fullmatch(core):
        return True
    return bool(_KANJI_RE.search(core))


def _pos_canonical_tokens(values: Iterable[str]) -> set[str]:
    tokens: set[str] = set()
    for raw in values:
        text = str(raw or "").strip()
        if not text:
            continue
        folded = text.casefold()
        tokens.add(folded)
        head = text.split("-")[0]
        mapped = _SUDACHI_POS_CANONICAL.get(head)
        if mapped:
            tokens.update(mapped)
        for sudachi, canonicals in _SUDACHI_POS_CANONICAL.items():
            if sudachi in text:
                tokens.update(canonicals)
    return {token for token in tokens if token}


def _pos_and_domain_values(
    record: dict[str, Any],
    candidate: dict[str, Any],
) -> tuple[list[str], list[str]]:
    pos_values: list[str] = []
    domain_values: list[str] = []
    for key in ("part_of_speech", "pos"):
        pos_values.extend(record.get(key) or [])
        pos_values.extend(candidate.get(key) or [])
    domain_values.extend(record.get("domains") or [])
    domain_values.extend(candidate.get("domains") or [])
    return pos_values, domain_values


def _blocks_pos_match_boost(
    record: dict[str, Any],
    candidate: dict[str, Any],
) -> bool:
    pos_values, domain_values = _pos_and_domain_values(record, candidate)
    if any(_normalize(value) in _POS_BOOST_BLOCK_VALUES for value in pos_values):
        return True
    return any(
        str(domain).casefold() == "proper-name"
        for domain in domain_values
        if domain
    )


def _is_proper_name_candidate(
    record: dict[str, Any],
    candidate: dict[str, Any],
) -> bool:
    pos_values, domain_values = _pos_and_domain_values(record, candidate)
    if any(_normalize(value) in _POS_BOOST_BLOCK_VALUES for value in pos_values):
        return True
    return any(
        str(domain).casefold() == "proper-name"
        for domain in domain_values
        if domain
    )


def _token_matches_proposition_head(token: Token, proposition: Proposition) -> bool:
    predicate = _normalize(proposition.predicate or "")
    if not predicate:
        return False
    token_forms = {
        _normalize(token.surface),
        _normalize(token.normalized),
    }
    if predicate in token_forms:
        return True
    # A サ変 noun realizes the head of its light-verb predicate, so 「変更」
    # heads 「変更する」. This is the grammatical relation, not a lexical entry.
    if "サ変可能" in token.pos:
        return any(
            form and predicate == f"{form}{_SURU_LIGHT_VERB}"
            for form in token_forms
        )
    return False


def _argument_indices_for_token(
    proposition: Proposition,
    token: Token,
) -> list[int]:
    return [
        index
        for index, argument in enumerate(proposition.arguments)
        if argument.span and _overlap(token.span, argument.span)
    ]


def _has_spanned_arguments(proposition: Proposition) -> bool:
    return any(argument.span for argument in proposition.arguments)


def _sense_confidence(margin: int, *, selected: bool) -> float:
    """Report how far the pack actually separated the top candidates.

    Tied candidates are ordered by candidate id, which carries no linguistic
    evidence. Reporting such a pick below the resolved floor keeps it
    distinguishable from a sense the context genuinely decided.
    """

    separation = max(0, margin) / 100
    if selected:
        return min(0.99, 0.70 + separation)
    return round(min(0.69, 0.50 + separation), 4)


def _headword_matches_token(record: dict[str, Any], token: Token) -> bool:
    token_forms = {
        _normalize(token.surface),
        _normalize(token.normalized),
    }
    lemma = _normalize(str(record.get("lemma") or ""))
    if lemma and lemma in token_forms:
        return True
    for surface in record.get("surfaces") or []:
        if _normalize(str(surface)) in token_forms:
            return True
    return False


def _candidate_label_texts(candidate: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    label = candidate.get("label")
    if label:
        texts.append(str(label))
    for gloss in candidate.get("glosses") or []:
        if gloss:
            texts.append(str(gloss))
    return texts


def _candidate_has_japanese_label(candidate: dict[str, Any]) -> bool:
    return any(_has_japanese_script(text) for text in _candidate_label_texts(candidate))


def _rank_sort_key(
    score: int,
    candidate_id: str,
    record: dict[str, Any],
    candidate: dict[str, Any],
    token: Token,
) -> tuple[int, int, int, str]:
    return (
        -score,
        0 if _candidate_has_japanese_label(candidate) else 1,
        0 if _headword_matches_token(record, token) else 1,
        candidate_id,
    )


def _neighbor_surfaces_for_token(
    tokens: list[Token],
    *,
    current: Token,
) -> list[str]:
    self_surfaces = {
        _normalize(current.surface),
        _normalize(current.normalized),
    }
    neighbors: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        for value in (token.surface, token.normalized):
            normalized = _normalize(value)
            if not normalized or len(normalized) <= 1:
                continue
            if normalized in self_surfaces:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            neighbors.append(value)
    return neighbors


class SemanticDataRuntime:
    """Approved-only runtime for unified lexical and context data packs.

    This runtime applies reviewed meaning candidates to MeaningGraph
    propositions. It preserves ambiguity and never creates external actions.
    """

    def __init__(
        self,
        root: Path,
        *,
        shard_cache_size: int = 4,
        record_cache_size: int = 256,
    ):
        self.root = Path(root)
        self.available = False
        self.manifest: dict[str, Any] = {}
        self.surface_index: dict[str, list[str]] = {}
        self.reading_index: dict[str, list[str]] = {}
        self.record_locator: dict[str, dict[str, int]] = {}
        self.shard_cache_size = max(1, shard_cache_size)
        self.record_cache_size = max(1, record_cache_size)
        self._shards: OrderedDict[int, dict[str, dict[str, Any]]] = OrderedDict()
        self._record_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._record_store: BinaryIO | None = None
        self._record_offsets: dict[str, tuple[int, int]] = {}
        self._record_store_lock = Lock()
        self._record_cache_lock = Lock()
        self.last_metrics: dict[str, int | float | str] = {
            "semantic_pack_available": 0,
            "semantic_pack_match_count": 0,
            "semantic_pack_resolved_count": 0,
            "semantic_pack_ambiguous_count": 0,
        }

        manifest_path = self.root / "manifest.json"
        if not manifest_path.exists():
            return
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("approved_only") is not True:
            raise ValueError("semantic data pack must be approved-only")
        if manifest.get("automatic_external_action") is not False:
            raise ValueError("semantic data pack external-action boundary is invalid")
        if manifest.get("preserve_ambiguity") is not True:
            raise ValueError("semantic data pack must preserve ambiguity")
        index_root = self.root / "indexes"
        required = {
            "surface": index_root / "surface-index.json.gz",
            "reading": index_root / "reading-index.json.gz",
            "locator": index_root / "record-locator.json.gz",
        }
        missing = [str(path) for path in required.values() if not path.exists()]
        if missing:
            raise FileNotFoundError(
                "compiled semantic data indexes are incomplete: " + ", ".join(missing)
            )
        runtime_required = {
            "surface": index_root / "runtime-surface-index.json.gz",
            "reading": index_root / "runtime-reading-index.json.gz",
            "locator": index_root / "runtime-record-locator.json.gz",
        }
        if "runtime_record_count" in manifest:
            runtime_missing = [
                str(path) for path in runtime_required.values() if not path.exists()
            ]
            if runtime_missing:
                raise FileNotFoundError(
                    "compiled semantic runtime indexes are incomplete: "
                    + ", ".join(runtime_missing)
                )
            selected_indexes = runtime_required
            expected_locator_count = int(manifest["runtime_record_count"])
        else:
            # Backward compatibility for compiler manifests created before
            # runtime-only lookup indexes were introduced.
            selected_indexes = required
            expected_locator_count = int(manifest.get("record_count", 0))

        self.manifest = manifest
        self.surface_index = _load_json_gzip(selected_indexes["surface"])
        self.reading_index = _load_json_gzip(selected_indexes["reading"])
        self.record_locator = _load_json_gzip(selected_indexes["locator"])
        if len(self.record_locator) != expected_locator_count:
            raise ValueError("semantic data record locator count mismatch")

        runtime_shards = {
            int(location["shard"])
            for location in self.record_locator.values()
        }
        if len(runtime_shards) > self.shard_cache_size:
            self._prepare_random_access_store()

        self.available = True
        self.last_metrics["semantic_pack_available"] = 1

    @property
    def record_count(self) -> int:
        return int(self.manifest.get("record_count", 0))

    @property
    def runtime_record_count(self) -> int:
        return int(self.manifest.get("runtime_record_count", self.record_count))

    @staticmethod
    def _validated_record(
        item: dict[str, Any],
        *,
        path: Path,
        line_number: int,
        expected_record_id: str | None = None,
    ) -> dict[str, Any]:
        record_id = item.get("record_id")
        if not record_id:
            raise ValueError(f"semantic record_id missing: {path}:{line_number}")
        if expected_record_id is not None and record_id != expected_record_id:
            raise ValueError(
                "semantic record locator mismatch: "
                f"expected={expected_record_id} actual={record_id} "
                f"path={path}:{line_number}"
            )
        approval = item.get("approval") or {}
        approved_scopes = approval.get("approved_scopes") or []
        if not approved_scopes:
            raise ValueError(f"semantic record has no approved scope: {record_id}")
        blocked = approval.get("blockers_by_scope") or {}
        if any(blocked.get(scope) for scope in approved_scopes):
            raise ValueError(
                f"approved semantic record contains scoped blocker: {record_id}"
            )
        return item

    def _prepare_random_access_store(self) -> None:
        """Materialize runtime rows once to avoid repeated full-shard JSON parsing.

        The compiled locator already identifies the exact line for every runtime
        record. When runtime records span more shards than the bounded parsed
        shard cache can retain, repeatedly parsing 10k-record gzip shards causes
        deterministic cache thrashing. This store scans each required shard once
        as bytes, keeps only runtime rows in a temporary seekable file, and
        records byte offsets. Runtime semantics and approval validation remain
        unchanged; individual rows are JSON-decoded and validated on access.
        """

        line_map_by_shard: dict[int, dict[int, str]] = {}
        for record_id, location in self.record_locator.items():
            shard = int(location["shard"])
            line_number = int(location["line"])
            shard_lines = line_map_by_shard.setdefault(shard, {})
            if line_number in shard_lines:
                raise ValueError(
                    "semantic runtime locator line collision: "
                    f"shard={shard} line={line_number}"
                )
            shard_lines[line_number] = record_id

        store = TemporaryFile(mode="w+b")
        offsets: dict[str, tuple[int, int]] = {}
        offset = 0
        try:
            for shard, requested_lines in sorted(line_map_by_shard.items()):
                path = self.root / "records" / f"records-{shard:04d}.jsonl.gz"
                if not path.exists():
                    raise FileNotFoundError(path)
                with gzip.open(path, "rb") as handle:
                    for line_number, line in enumerate(handle, 1):
                        record_id = requested_lines.get(line_number)
                        if record_id is None:
                            continue
                        offsets[record_id] = (offset, len(line))
                        store.write(line)
                        offset += len(line)
            if len(offsets) != len(self.record_locator):
                missing = sorted(set(self.record_locator) - set(offsets))
                raise ValueError(
                    "semantic runtime locator could not materialize all records: "
                    f"missing={missing[:20]}"
                )
            store.flush()
        except Exception:
            store.close()
            raise

        self._record_store = store
        self._record_offsets = offsets

    def _load_shard(self, number: int) -> dict[str, dict[str, Any]]:
        cached = self._shards.get(number)
        if cached is not None:
            self._shards.move_to_end(number)
            return cached
        path = self.root / "records" / f"records-{number:04d}.jsonl.gz"
        if not path.exists():
            raise FileNotFoundError(path)
        records: dict[str, dict[str, Any]] = {}
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                item = self._validated_record(
                    json.loads(line),
                    path=path,
                    line_number=line_number,
                )
                records[item["record_id"]] = item
        self._shards[number] = records
        self._shards.move_to_end(number)
        while len(self._shards) > self.shard_cache_size:
            self._shards.popitem(last=False)
        return records

    def _record(self, record_id: str) -> dict[str, Any]:
        location = self.record_locator.get(record_id)
        if location is None:
            raise KeyError(record_id)

        if self._record_store is not None:
            with self._record_cache_lock:
                cached = self._record_cache.get(record_id)
                if cached is not None:
                    self._record_cache.move_to_end(record_id)
                    return cached

            span = self._record_offsets.get(record_id)
            if span is None:
                raise KeyError(record_id)
            offset, length = span
            with self._record_store_lock:
                self._record_store.seek(offset)
                payload = self._record_store.read(length)
            if len(payload) != length:
                raise ValueError(
                    f"semantic runtime record cache truncated: {record_id}"
                )
            path = (
                self.root
                / "records"
                / f"records-{int(location['shard']):04d}.jsonl.gz"
            )
            item = self._validated_record(
                json.loads(payload),
                path=path,
                line_number=int(location["line"]),
                expected_record_id=record_id,
            )
            with self._record_cache_lock:
                existing = self._record_cache.get(record_id)
                if existing is not None:
                    self._record_cache.move_to_end(record_id)
                    return existing
                self._record_cache[record_id] = item
                self._record_cache.move_to_end(record_id)
                while len(self._record_cache) > self.record_cache_size:
                    self._record_cache.popitem(last=False)
            return item

        item = self._load_shard(int(location["shard"])).get(record_id)
        if item is None:
            raise KeyError(record_id)
        return item

    def lookup_token(self, token: Token, *, max_candidates: int = 32) -> list[dict[str, Any]]:
        if not self.available:
            return []
        keys = [_normalize(token.surface), _normalize(token.normalized)]
        record_ids: list[str] = []
        for key in keys:
            for record_id in self.surface_index.get(key, []):
                if record_id not in record_ids:
                    record_ids.append(record_id)
        if not record_ids and token.reading:
            for record_id in self.reading_index.get(_normalize(token.reading), []):
                if record_id not in record_ids:
                    record_ids.append(record_id)
        return [self._record(record_id) for record_id in record_ids[:max_candidates]]

    @staticmethod
    def _context_score(
        record: dict[str, Any],
        candidate: dict[str, Any],
        *,
        token: Token,
        context_text: str,
        social_markers: set[str],
        discourse_markers: set[str],
        neighbor_surfaces: Iterable[str] = (),
        neighbor_definitions: str = "",
        known_entities: Iterable[str] = (),
    ) -> tuple[int, list[str]]:
        score = 100
        evidence = ["semantic_pack_surface_match"]
        if not _blocks_pos_match_boost(record, candidate):
            token_pos = _pos_canonical_tokens(token.pos)
            record_pos = _pos_canonical_tokens(
                [
                    *record.get("part_of_speech", []),
                    *record.get("pos", []),
                    *candidate.get("part_of_speech", []),
                    *candidate.get("pos", []),
                ]
            )
            if token_pos and record_pos and token_pos.intersection(record_pos):
                score += 20
                evidence.append("semantic_pack_pos_match")

        label_texts = _candidate_label_texts(candidate)
        if any(_has_japanese_script(text) for text in label_texts):
            score += 25
            evidence.append("semantic_pack_japanese_label")

        if _is_proper_name_candidate(record, candidate):
            known = {_normalize(str(value)) for value in known_entities if str(value)}
            if _normalize(token.surface) not in known:
                score -= 40
                evidence.append("semantic_pack_proper_name_demotion")

        if any(
            marker in text
            for text in label_texts
            for marker in _EVERYDAY_SENSE_MARKERS
        ):
            score += 20
            evidence.append("semantic_pack_everyday_sense")

        label = candidate.get("label")
        if label:
            core = _label_core(str(label))
            token_forms = {
                _normalize(token.surface),
                _normalize(token.normalized),
                _normalize(str(record.get("lemma") or "")),
            }
            token_forms = {value for value in token_forms if value}
            if (
                core
                and core not in token_forms
                and _is_distinct_japanese_word_core(core)
                and not re.search(r"[\u3040-\u309F]", core)
                and not any(form and form in core for form in token_forms)
            ):
                score -= 15
                evidence.append("semantic_pack_distinct_label_penalty")

        token_head = _normalize(token.surface)
        record_lemma = _normalize(str(record.get("lemma") or ""))
        if token_head == _WEATHER_SURFACE or record_lemma == _WEATHER_SURFACE:
            if any(
                marker in text
                for text in label_texts
                for marker in _WEATHER_LABEL_MARKERS
            ):
                score += 15
                evidence.append("semantic_pack_weather_headword")
            if any(
                marker in text
                for text in label_texts
                for marker in _WEATHER_NON_METEOROLOGY_MARKERS
            ):
                score -= 25
                evidence.append("semantic_pack_weather_non_meteorology_penalty")

        conditions = dict(record.get("context_conditions") or {})
        candidate_context = candidate.get("context") or {}
        for key in (
            "required_any",
            "required_all",
            "forbidden_any",
            "required_social",
            "required_discourse",
        ):
            if key in candidate_context:
                conditions[key] = [
                    *conditions.get(key, []),
                    *candidate_context.get(key, []),
                ]
        required_all = conditions.get("required_all", [])
        required_any = conditions.get("required_any", [])
        forbidden_any = conditions.get("forbidden_any", [])
        if required_all:
            if not _contains_all(context_text, required_all):
                return -10000, ["semantic_pack_required_all_missing"]
            score += 40
            evidence.append("semantic_pack_required_all")
        if required_any:
            if not _contains_any(context_text, required_any):
                return -10000, ["semantic_pack_required_any_missing"]
            score += 25
            evidence.append("semantic_pack_required_any")
        if forbidden_any and _contains_any(context_text, forbidden_any):
            return -10000, ["semantic_pack_forbidden_context"]

        required_social = conditions.get("required_social", [])
        if required_social:
            if not _has_required_markers(required_social, social_markers):
                return -10000, ["semantic_pack_required_social_missing"]
            score += 15
            evidence.append("semantic_pack_required_social")

        required_discourse = conditions.get("required_discourse", [])
        if required_discourse:
            if not _has_required_markers(required_discourse, discourse_markers):
                return -10000, ["semantic_pack_required_discourse_missing"]
            score += 15
            evidence.append("semantic_pack_required_discourse")

        domains = [*record.get("domains", []), *candidate.get("domains", [])]
        matched_domain = next(
            (
                domain
                for domain in domains
                if domain and domain.casefold() in context_text.casefold()
            ),
            None,
        )
        if matched_domain:
            score += 10
            evidence.append(f"semantic_pack_domain:{matched_domain}")
        if candidate.get("evidence_ids"):
            score += 1
            evidence.append("semantic_pack_evidence_complete")

        context_texts = _candidate_context_texts(record, candidate)
        if context_texts and neighbor_surfaces:
            folded_texts = [_normalize(text) for text in context_texts]
            for neighbor in neighbor_surfaces:
                folded_neighbor = _normalize(str(neighbor))
                if not folded_neighbor or len(folded_neighbor) <= 1:
                    continue
                if any(folded_neighbor in text for text in folded_texts):
                    score += 30
                    evidence.append("semantic_pack_example_overlap")
                    break

        if neighbor_definitions.strip() and context_texts:
            overlap_bonus, matched = _neighbor_definition_overlap_bonus(
                context_texts,
                neighbor_definitions,
                token=token,
            )
            if matched:
                score += overlap_bonus
                evidence.append("semantic_pack_neighbor_definition_overlap")

        return score, evidence

    @staticmethod
    def _collocate_adjusted_context_score(
        record: dict[str, Any],
        candidate: dict[str, Any],
        *,
        token: Token,
        tokens: list[Token],
        context_text: str,
        social_markers: set[str],
        discourse_markers: set[str],
        neighbor_surfaces: Iterable[str] = (),
        neighbor_definitions: str = "",
        known_entities: Iterable[str] = (),
    ) -> tuple[int, list[str]]:
        score, evidence = SemanticDataRuntime._context_score(
            record,
            candidate,
            token=token,
            context_text=context_text,
            social_markers=social_markers,
            discourse_markers=discourse_markers,
            neighbor_surfaces=neighbor_surfaces,
            neighbor_definitions=neighbor_definitions,
            known_entities=known_entities,
        )
        adjustment, adjustment_evidence = _collocate_sense_adjustment(
            candidate,
            token=token,
            tokens=tokens,
            neighbor_definitions=neighbor_definitions,
        )
        if adjustment:
            score += adjustment
            evidence.extend(adjustment_evidence)
        return score, evidence

    @staticmethod
    def _apply_parameters(
        proposition: Proposition,
        candidate: dict[str, Any],
    ) -> Proposition:
        parameters = dict(candidate.get("parameters") or {})
        allowed_scalar = {
            "force_level",
            "directness",
            "politeness_level",
            "speech_act",
            "epistemic_status",
            "information_territory",
        }
        update: dict[str, Any] = {}
        for key in allowed_scalar:
            if key in parameters and parameters[key] is not None:
                update[key] = parameters[key]
        polarity = candidate.get("polarity")
        if polarity in {"positive", "negative"}:
            update["polarity"] = polarity
        list_fields = {
            "register_labels",
            "honorific_classes",
            "interaction_functions",
            "pragmatic_markers",
        }
        for key in list_fields:
            values = parameters.get(key)
            if values:
                update[key] = list(
                    dict.fromkeys([*getattr(proposition, key), *values])
                )
        if parameters.get("sensory_features"):
            update["sensory_features"] = {
                **proposition.sensory_features,
                **parameters["sensory_features"],
            }
        return proposition.model_copy(update=update) if update else proposition

    def _apply_argument_senses(
        self,
        proposition: Proposition,
        *,
        argument_indices: list[int],
        sense_candidates: list[SenseCandidate],
        top: tuple[int, str, dict[str, Any], dict[str, Any], list[str]],
        margin: int,
        selected: bool,
        action_sensitive: bool,
        structural_intent: bool,
        token: Token,
        ranked: list[tuple[int, str, dict[str, Any], dict[str, Any], list[str]]],
        unresolved: list[dict[str, Any]],
    ) -> Proposition:
        """Attach a ranked sense to the arguments the token realizes.

        Candidate parameters stay on the predicate path: register, politeness
        and speech act describe the proposition, not the filler of one of its
        argument slots.
        """

        arguments = list(proposition.arguments)
        changed = False
        escalated = False
        for argument_index in argument_indices:
            argument = arguments[argument_index]
            if argument.sense_id is not None:
                existing_score = next(
                    (
                        candidate.score
                        for candidate in argument.sense_candidates
                        if candidate.sense_id == argument.sense_id
                    ),
                    None,
                )
                if existing_score is not None and top[0] <= existing_score:
                    continue
            if selected or (not action_sensitive and not structural_intent):
                arguments[argument_index] = argument.model_copy(update={
                    "sense_id": top[1],
                    "sense_label": top[3].get("label") or top[1],
                    "sense_confidence": _sense_confidence(
                        margin,
                        selected=selected,
                    ),
                    "sense_candidates": sense_candidates,
                })
                changed = True
                continue
            # Same boundary as the predicate path: ordinary polysemy under a
            # structural intent stays lexical evidence, while action and social
            # risk leaves the argument unresolved and fail-closed.
            if structural_intent and not action_sensitive:
                continue
            arguments[argument_index] = argument.model_copy(update={
                "sense_id": None,
                "sense_label": None,
                "sense_confidence": 0.0,
                "sense_candidates": sense_candidates,
                "status": ItemStatus.AMBIGUOUS,
            })
            changed = True
            escalated = True

        if not changed:
            return proposition

        update: dict[str, Any] = {
            "arguments": arguments,
            "evidence_ids": list(dict.fromkeys([
                *proposition.evidence_ids,
                *top[3].get("evidence_ids", []),
                f"semantic-pack:{top[2]['record_id']}",
            ])),
            "inference_sources": list(dict.fromkeys([
                *proposition.inference_sources,
                "approved-semantic-data-pack",
            ])),
        }
        if escalated:
            unresolved.append({
                "type": "semantic_data_pack",
                "surface": token.surface,
                "candidate_ids": [item[1] for item in ranked],
                "status": ItemStatus.AMBIGUOUS.value,
                "action_sensitive": action_sensitive,
            })
            if action_sensitive:
                update["executable_candidate"] = False
        return proposition.model_copy(update=update)

    def enrich(
        self,
        graph: MeaningGraph,
        *,
        tokens: list[Token],
        original_text: str,
        conversation_context: list[str],
        known_entities: list[str],
        social_context: SocialContext | None = None,
        discourse_state: dict[str, Any] | None = None,
        update_hash: bool = True,
    ) -> MeaningGraph:
        if not self.available:
            quality = {
                **graph.quality_annotations,
                "semantic_data_pack_used": False,
                "semantic_data_pack_record_count": 0,
            }
            updated = graph.model_copy(update={"quality_annotations": quality})
            if update_hash:
                return updated.model_copy(update={
                    "semantic_hash": _stable_hash(updated),
                })
            return updated

        if self.runtime_record_count == 0:
            quality = {
                **graph.quality_annotations,
                "semantic_data_pack_used": True,
                "semantic_data_pack_record_count": self.record_count,
                "semantic_data_runtime_record_count": 0,
                "semantic_data_pack_match_count": 0,
                "semantic_data_pack_resolved_count": 0,
                "semantic_data_pack_ambiguous_count": 0,
                "semantic_data_pack_automatic_external_action": False,
            }
            self.last_metrics = {
                "semantic_pack_available": 1,
                "semantic_pack_match_count": 0,
                "semantic_pack_resolved_count": 0,
                "semantic_pack_ambiguous_count": 0,
            }
            updated = graph.model_copy(update={"quality_annotations": quality})
            if update_hash:
                return updated.model_copy(update={
                    "semantic_hash": _stable_hash(updated),
                })
            return updated

        context_text = "\n".join([original_text, *conversation_context, *known_entities])
        known_entity_markers = {_normalize(str(value)) for value in known_entities if str(value)}
        social_markers = _social_markers(social_context)
        discourse_markers = _discourse_markers(graph, discourse_state)
        propositions = list(graph.propositions)
        language_features = list(graph.language_features)
        unresolved = list(graph.unresolved)
        match_count = 0
        resolved_count = 0
        ambiguous_count = 0

        # A proposition sense describes its predicate, so decide up front which
        # propositions actually have a head token in this sentence. Predicates
        # never change during enrichment, so this survives the copies below.
        content_tokens = [
            token for token in tokens if not _is_function_word_token(token)
        ]
        head_bearing = [
            any(
                _token_matches_proposition_head(token, proposition)
                for token in content_tokens
            )
            for proposition in propositions
        ]
        role_structured = [
            _has_spanned_arguments(proposition) for proposition in propositions
        ]

        neighbor_definition_by_span_start: dict[int, str] = {}
        for content_token in content_tokens:
            definition_parts: list[str] = []
            for neighbor_record in self.lookup_token(content_token):
                definition_parts.extend(
                    _record_lookup_definition_texts(neighbor_record)
                )
            if definition_parts:
                neighbor_definition_by_span_start[content_token.span.start] = (
                    "\n".join(definition_parts)
                )

        for token in tokens:
            if _is_function_word_token(token):
                continue
            neighbor_surfaces = _neighbor_surfaces_for_token(tokens, current=token)
            neighbor_definitions = _case_linked_neighbor_definitions(
                tokens,
                current=token,
                neighbor_definition_by_span_start=neighbor_definition_by_span_start,
            )
            records = self.lookup_token(token)
            if not records:
                continue
            related_indices = [
                index
                for index, proposition in enumerate(propositions)
                if _overlap(token.span, proposition.source_span)
                or any(
                    argument.span and _overlap(token.span, argument.span)
                    for argument in proposition.arguments
                )
            ]
            ranked: list[
                tuple[int, str, dict[str, Any], dict[str, Any], list[str]]
            ] = []
            for record in records:
                record_discourse_markers = set(discourse_markers)
                feature_type = record.get("feature_type") or ""
                if feature_type:
                    record_discourse_markers.add(
                        _normalize(f"feature:{feature_type}")
                    )
                for candidate in record.get("meaning_candidates", []):
                    if candidate.get("review_status") != "approved":
                        continue
                    score, evidence = self._collocate_adjusted_context_score(
                        record,
                        candidate,
                        token=token,
                        tokens=tokens,
                        context_text=context_text,
                        social_markers=social_markers,
                        discourse_markers=record_discourse_markers,
                        neighbor_surfaces=neighbor_surfaces,
                        neighbor_definitions=neighbor_definitions,
                        known_entities=known_entity_markers,
                    )
                    if score <= -10000:
                        continue
                    ranked.append(
                        (score, candidate["candidate_id"], record, candidate, evidence)
                    )
            if not ranked:
                continue
            ranked.sort(
                key=lambda item: _rank_sort_key(
                    item[0],
                    item[1],
                    item[2],
                    item[3],
                    token,
                )
            )
            match_count += 1
            sense_candidates = [
                SenseCandidate(
                    sense_id=item[1],
                    label=item[3].get("label") or item[1],
                    score=item[0],
                    evidence=item[4],
                )
                for item in ranked
            ]
            top = ranked[0]
            margin = top[0] - ranked[1][0] if len(ranked) > 1 else top[0]
            selected = len(ranked) == 1 or margin >= 20
            action_sensitive = any(
                item[2].get("risk_class") in {"action", "social"}
                for item in ranked
            )
            if selected:
                resolved_count += 1
            else:
                ambiguous_count += 1

            for index in related_indices:
                proposition = propositions[index]
                # A proposition sense states what its predicate means, so only a
                # head token may write it. A token that realizes an argument
                # describes that argument instead. Without this split every
                # content token in the clause overlaps the proposition span and
                # the last one processed silently became the predicate sense.
                if _token_matches_proposition_head(token, proposition):
                    argument_indices: list[int] = []
                else:
                    argument_indices = _argument_indices_for_token(
                        proposition,
                        token,
                    )
                    if not argument_indices:
                        # Fall back to the clause only when the graph offers no
                        # finer attachment point at all: no role-bearing
                        # argument spans and no head token in this sentence.
                        if role_structured[index] or head_bearing[index]:
                            continue
                structural_intent = (
                    proposition.intent_type in ACTION_INTENTS
                    or proposition.intent_type in CONSTRAINT_INTENTS
                )
                if argument_indices:
                    propositions[index] = self._apply_argument_senses(
                        proposition,
                        argument_indices=argument_indices,
                        sense_candidates=sense_candidates,
                        top=top,
                        margin=margin,
                        selected=selected,
                        action_sensitive=action_sensitive,
                        structural_intent=structural_intent,
                        token=token,
                        ranked=ranked,
                        unresolved=unresolved,
                    )
                    continue
                # The system semantic profile runs before the approved data pack
                # and may already have a stronger, context-specific resolution.
                # A later lexical/context pack can add coverage, but it must not
                # replace an already resolved sense with a weaker generic sense.
                if _inference_sources_profile_locked(
                    proposition.inference_sources
                ):
                    continue
                if proposition.sense_id is not None:
                    existing_score = next(
                        (
                            candidate.score
                            for candidate in proposition.sense_candidates
                            if candidate.sense_id == proposition.sense_id
                        ),
                        None,
                    )
                    if existing_score is not None and top[0] <= existing_score:
                        continue
                if selected or (not action_sensitive and not structural_intent):
                    proposition = proposition.model_copy(update={
                        "sense_id": top[1],
                        "sense_label": top[3].get("label") or top[1],
                        "sense_confidence": _sense_confidence(
                            margin,
                            selected=selected,
                        ),
                        "sense_candidates": sense_candidates,
                        "evidence_ids": list(dict.fromkeys([
                            *proposition.evidence_ids,
                            *top[3].get("evidence_ids", []),
                            f"semantic-pack:{top[2]['record_id']}",
                        ])),
                        "inference_sources": list(dict.fromkeys([
                            *proposition.inference_sources,
                            "approved-semantic-data-pack",
                        ])),
                    })
                    proposition = self._apply_parameters(proposition, top[3])
                else:
                    # Grammar-derived action and constraint intents are already
                    # structural decisions. Ordinary lexical/semantic polysemy
                    # remains available as lexical evidence but must not turn a
                    # resolved structural proposition into an ambiguous one.
                    # Action/social-risk ambiguity still crosses this boundary
                    # and remains fail-closed for external execution.
                    if structural_intent and not action_sensitive:
                        continue
                    proposition = proposition.model_copy(update={
                        "sense_id": None,
                        "sense_label": None,
                        "sense_confidence": 0.0,
                        "sense_candidates": sense_candidates,
                        "status": ItemStatus.AMBIGUOUS,
                        "executable_candidate": (
                            False
                            if action_sensitive
                            else proposition.executable_candidate
                        ),
                    })
                    unresolved.append({
                        "type": "semantic_data_pack",
                        "surface": token.surface,
                        "candidate_ids": [item[1] for item in ranked],
                        "status": ItemStatus.AMBIGUOUS.value,
                        "action_sensitive": action_sensitive,
                    })
                propositions[index] = proposition

            eligible_record_ids = {item[2]["record_id"] for item in ranked}
            for record in records:
                if "language_feature" not in record.get("semantic_targets", []):
                    continue
                if record["record_id"] not in eligible_record_ids:
                    continue
                attach_primary = selected or not action_sensitive
                selected_candidate = (
                    top[3]
                    if attach_primary and top[2]["record_id"] == record["record_id"]
                    else None
                )
                language_features.append(LanguageFeatureMatch(
                    entry_id=record["record_id"],
                    feature_type=record.get("feature_type") or "semantic_data",
                    surface=token.surface,
                    interpretation_id=(
                        selected_candidate.get("candidate_id")
                        if selected_candidate
                        else None
                    ),
                    interpretation=(
                        selected_candidate.get("label")
                        if selected_candidate
                        else None
                    ),
                    parameters=(selected_candidate or {}).get("parameters", {}),
                    register_profile=(selected_candidate or {}).get(
                        "register",
                        record.get("register", {}),
                    ),
                    source_span=token.span,
                    status=(
                        ItemStatus.RESOLVED
                        if selected_candidate
                        else ItemStatus.AMBIGUOUS
                    ),
                    candidate_ids=[
                        item[1]
                        for item in ranked
                        if item[2]["record_id"] == record["record_id"]
                    ],
                    evidence_ids=(selected_candidate or {}).get("evidence_ids", []),
                    risk_class=record.get("risk_class", "semantic"),
                ))

        quality = {
            **graph.quality_annotations,
            "semantic_data_pack_used": True,
            "semantic_data_pack_record_count": self.record_count,
            "semantic_data_runtime_record_count": self.runtime_record_count,
            "semantic_data_pack_match_count": match_count,
            "semantic_data_pack_resolved_count": resolved_count,
            "semantic_data_pack_ambiguous_count": ambiguous_count,
            "semantic_data_pack_automatic_external_action": False,
        }
        updated = graph.model_copy(update={
            "propositions": propositions,
            "language_features": language_features,
            "unresolved": unresolved,
            "quality_annotations": quality,
        })
        if update_hash:
            updated = updated.model_copy(update={
                "semantic_hash": _stable_hash(updated),
            })
        self.last_metrics = {
            "semantic_pack_available": 1,
            "semantic_pack_match_count": match_count,
            "semantic_pack_resolved_count": resolved_count,
            "semantic_pack_ambiguous_count": ambiguous_count,
        }
        return updated
