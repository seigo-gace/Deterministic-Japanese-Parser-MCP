from __future__ import annotations

import hashlib
import re

from .grammar_kernel import quote_ranges
from .models import (
    Argument,
    ArgumentComponent,
    ArgumentEdge,
    ArgumentationResult,
    AttributionFrame,
    Clause,
    DependencyArc,
    DiscourseRelation,
    Entity,
    ItemStatus,
    MeaningGraph,
    OriginalSpan,
    ParagraphFrame,
    ParagraphStructure,
    PredicateFrame,
    Proposition,
    ReadingAnalysis,
    ScopeOperator,
    SummaryResult,
    Token,
)


_PREDICATE_POS = {"動詞", "形容詞", "形状詞"}
_COPULAS = {"だ", "です", "である", "だった", "でした"}
_ASPECT_AUXILIARIES = {
    "居る",
    "有る",
    "置く",
    "仕舞う",
    "見る",
    "来る",
    "行く",
}
_POLITE_REQUEST_AUXILIARIES = frozenset({
    "下さる",
    "呉れる",
    "くれる",
    "貰う",
    "もらう",
    "頂く",
    "いただく",
    "欲しい",
    "ほしい",
})
_POLITE_REQUEST_TAIL_SURFACES = frozenset({
    "ください",
    "下さい",
    "ください。",
    "下さい。",
})
_WH_COPULA_HEADS = frozenset({"何", "誰", "なに", "だれ", "なん"})
_STRUCTURAL_PROPOSITION_INTENTS = frozenset({
    "reference",
    "question",
    "condition",
    "action",
})
_GRATITUDE_RE = re.compile(r"ありがとう(?:ございます)?")
_CAPABILITY_QUESTION_RE = re.compile(
    r"(?:できますか|可能ですか|対応可能でしょうか)"
)
_CASE_ROLES = {
    "が": "agent",
    "は": "topic",
    "を": "object",
    "に": "recipient",
    "へ": "destination",
    "で": "location_or_means",
    "から": "source",
    "まで": "limit",
    "より": "comparison_source",
    "と": "companion_or_quote",
}
_BOUNDARY = re.compile(r"^[、。！？!?；;：:]$")
_PARAGRAPH_BOUNDARY = re.compile(r"(?:\r?\n[ \t]*){2,}")

_NEGATION_PATTERNS = (
    (re.compile(r"わけではない"), "partial_negation"),
    (re.compile(r"とは限らない"), "limited_negation"),
    (re.compile(r"(?:なくはない|ないことはない)"), "double_negation"),
    (re.compile(r"必ずしも.{0,32}?ない"), "partial_negation"),
    (re.compile(r"決して.{0,32}?ない"), "strong_negation"),
    (re.compile(r"(?:あまり|ほとんど).{0,24}?ない"), "degree_negation"),
    (re.compile(r"(?:ではない|じゃない|ません|なかった|ない|ぬ|ず)"), "negation"),
)
_CONDITION_PATTERNS = (
    (re.compile(r"(?:れば|けば|えば|せば|なければ)"), "general_condition"),
    (re.compile(r"たら(?!しい)"), "event_condition"),
    (re.compile(r"なら(?:ば)?"), "premise_condition"),
    (re.compile(r"の場合(?:は|に)?"), "premise_condition"),
    (re.compile(r"(?<=[^\s、])場合(?:だけ)?(?:は|に)?"), "premise_condition"),
    (re.compile(r"(?:限り|まで)"), "general_condition"),
    (re.compile(r"(?:の際|際)(?:は|に)?"), "event_condition"),
    (re.compile(r"(?:とき|時)(?:は|に)"), "event_condition"),
    (re.compile(r"にもかかわらず"), "concessive_condition"),
    (re.compile(r"と(?=[、,])"), "natural_condition"),
    (re.compile(r"(?:ても|でも)"), "concessive_condition"),
)
_MODALITY_PATTERNS = (
    (re.compile(r"(?:だろう|でしょう|かもしれない)"), "inference"),
    (re.compile(r"(?:らしい|そうだ|とのことだ?)"), "hearsay"),
    (re.compile(r"(?:はずだ|はずです)"), "expectation"),
    (re.compile(r"(?:なければならない|べきだ?|必要がある|必須)"), "obligation"),
    (re.compile(r"(?:てもよい|てもいい|許可する)"), "permission"),
    (re.compile(r"(?:てはいけない|禁止する|するな)"), "prohibition"),
    (re.compile(r"(?:つもりだ|ようと思う)"), "intention"),
    (re.compile(r"(?:たい|てほしい)"), "desire"),
)
_QUANTIFIER_PATTERNS = (
    (re.compile(r"すべて|全て|全部|必ず"), "universal"),
    (re.compile(r"(?:のみ|だけ)(?=.{0,8}(?:完了|終了|成功))"), "restrictive"),
    (re.compile(r"(?:一部|いくつか|少なくとも)"), "existential_or_lower_bound"),
    (re.compile(r"(?:最大で|多くとも|以下|未満)"), "upper_bound"),
    (re.compile(r"(?:以上|を超える)"), "lower_bound"),
    (re.compile(r"(?:多くの|ほとんど|主に|おおむね)"), "proportional"),
)
_POLITE_REQUEST = re.compile(
    r"(?:して|していただけ|してもらえ)"
    r"(?:ますか|ませんか|ないでしょうか)"
)
_DISCOURSE_MARKERS = (
    (re.compile(r"^(?:そのため|だから|従って|よって|結果として)"), "causes"),
    (re.compile(r"^(?:しかし|ただし|一方|ところが|もっとも)"), "contrasts_with"),
    (re.compile(r"^(?:つまり|すなわち|言い換えると)"), "rephrases"),
    (re.compile(r"^(?:具体的には|例えば|たとえば)"), "exemplifies"),
    (re.compile(r"^(?:なぜなら|というのも)"), "justifies"),
    (re.compile(r"^(?:また|さらに|加えて)"), "adds"),
    (re.compile(r"^(?:したがって|以上のことから|結論として)"), "concludes"),
)
_PREVIOUS_TAIL_DISCOURSE_MARKERS = (
    (re.compile(r"(?:ので|ため)$"), "causes"),
    (re.compile(r"(?:のに|けれども|けれど|けど|が、?)$"), "contrasts_with"),
)


def _stable_hash(graph: MeaningGraph) -> str:
    return hashlib.sha256(
        graph.model_dump_json(exclude={"semantic_hash"}).encode("utf-8")
    ).hexdigest()


def _span(start: int, end: int, original: str) -> OriginalSpan:
    return OriginalSpan(start=start, end=end, source_text=original[start:end])


def _compact(value: str) -> str:
    return re.sub(r"[\s、。！？!?「」『』\"'()（）]+", "", value or "")


def _pos0(token: Token) -> str:
    return token.pos[0] if token.pos else ""


def _is_punctuation(token: Token) -> bool:
    return _pos0(token) in {"補助記号", "空白"} or bool(
        _BOUNDARY.match(token.surface)
    )


def _clause_token_indices(clause: Clause, tokens: list[Token]) -> list[int]:
    return [
        index
        for index, token in enumerate(tokens)
        if token.span.start < clause.source_span.end
        and clause.source_span.start < token.span.end
    ]


def _predicate_heads(indices: list[int], tokens: list[Token]) -> list[int]:
    heads: list[int] = []
    for position, index in enumerate(indices):
        token = tokens[index]
        if _pos0(token) in _PREDICATE_POS:
            previous = tokens[indices[position - 1]] if position else None
            previous_surface = "".join(
                tokens[item].surface for item in indices[max(0, position - 4):position]
            )
            if (
                token.normalized in {"無い", "ない"}
                and ("では" in previous_surface or "じゃ" in previous_surface)
            ):
                continue
            if (
                token.normalized in _ASPECT_AUXILIARIES
                and previous is not None
                and previous.surface in {"て", "で"}
            ):
                continue
            if (
                token.normalized in _POLITE_REQUEST_AUXILIARIES
                and previous is not None
                and previous.surface in {"て", "で"}
            ):
                continue
            if token.surface.rstrip("。！？!?") in _POLITE_REQUEST_TAIL_SURFACES:
                continue
            next_token = (
                tokens[indices[position + 1]]
                if position + 1 < len(indices)
                else None
            )
            if previous is not None and previous.surface == "に":
                if token.surface in {"よって", "因って", "依って"}:
                    continue
                if token.normalized in {"よる", "因る", "依る"} and (
                    next_token is not None and next_token.surface == "て"
                ):
                    continue
            heads.append(index)
            continue
        if _pos0(token) == "名詞" and position + 1 < len(indices):
            following = tokens[indices[position + 1]]
            if following.surface in _COPULAS:
                heads.append(index)
                continue
            tail = "".join(
                tokens[indices[item]].surface
                for item in range(position + 1, len(indices))
            )
            if re.search(r"(?:でしょう|だろう)か", tail):
                heads.append(index)
            continue
        if token.surface in _WH_COPULA_HEADS:
            heads.append(index)
    return heads


def _substantive_predicate_frames(frames: list[PredicateFrame]) -> list[PredicateFrame]:
    substantive = [
        frame
        for frame in frames
        if frame.predicate not in _POLITE_REQUEST_AUXILIARIES
    ]
    if not substantive:
        return frames
    lexical = [
        frame
        for frame in substantive
        if not re.fullmatch(r"(?:長|短|高|低|大|小|早|遅|多|少)い", frame.predicate)
    ]
    return lexical or substantive


def _primary_predicate_frame(frames: list[PredicateFrame]) -> PredicateFrame:
    substantive = _substantive_predicate_frames(frames)
    return substantive[-1]


def _overlap_span(left: OriginalSpan, right: OriginalSpan) -> bool:
    return left.start < right.end and right.start < left.end


def _clause_needs_matrix_observation(
    related: list[Proposition],
    clause_frames: list[PredicateFrame],
    main: PredicateFrame,
    *,
    clause_text: str,
) -> bool:
    if not clause_frames:
        return False
    if not related:
        return True
    if any(
        item.intent_type == "observation"
        and item.predicate == main.predicate
        for item in related
    ):
        return False
    if any(item.intent_type == "action" for item in related):
        return False
    if all(item.intent_type in _STRUCTURAL_PROPOSITION_INTENTS for item in related):
        return True
    premise_conditional = "もし" in clause_text or "なら" in clause_text
    if (
        premise_conditional
        and any(
            item.intent_type in {"condition", "action"}
            for item in related
        )
        and main.predicate not in {item.predicate for item in related}
    ):
        return True
    return False


def _align_observation_propositions_with_frames(
    propositions: list[Proposition],
    frame_by_clause: dict[str, list[PredicateFrame]],
) -> list[Proposition]:
    updated = list(propositions)
    for index, proposition in enumerate(updated):
        if proposition.intent_type != "observation" or not proposition.clause_id:
            continue
        clause_frames = frame_by_clause.get(proposition.clause_id, [])
        if not clause_frames:
            continue
        main = _primary_predicate_frame(clause_frames)
        if proposition.predicate == main.predicate:
            continue
        if len(clause_frames) == 1 or _overlap_span(
            proposition.source_span,
            main.source_span,
        ):
            updated[index] = proposition.model_copy(update={
                "predicate": main.predicate,
                "surface_predicate": main.surface_predicate,
                "arguments": main.arguments or proposition.arguments,
                "source_span": main.source_span,
            })
    return updated


def _ensure_gratitude_proposition(
    propositions: list[Proposition],
    clauses: list[Clause],
    original_text: str,
) -> list[Proposition]:
    match = _GRATITUDE_RE.search(original_text)
    if not match:
        return propositions
    if any(item.predicate == "感謝する" for item in propositions):
        return propositions
    clause = clauses[0] if clauses else None
    proposition = Proposition(
        proposition_id=f"P-{len(propositions) + 1:03d}",
        predicate="感謝する",
        surface_predicate=match.group(0),
        intent_type="observation",
        value=original_text.strip(),
        polarity="positive",
        sentence_mood="declarative",
        speech_act="gratitude",
        epistemic_status="asserted",
        executable_candidate=False,
        clause_id=clause.clause_id if clause else None,
        source_span=_span(match.start(), match.end(), original_text),
        evidence_ids=["READING:GRATITUDE"],
        inference_sources=["deterministic-reading-runtime"],
    )
    return [*propositions, proposition]


_COMPLETION_WITH_HOLDING_RE = re.compile(
    r"(?:を)?もって(?:完了|終了)(?:と(?:する|みなす)|と(?:する|みなす)?)"
)
_COMPLETION_ONLY_RE = re.compile(
    r"(?:のみ|だけ)(?:完了|終了)(?:です|だ|である)?"
)
_COMPLETION_CRITERIA_NOMINAL_RE = re.compile(
    r"(?:全(?:件|テスト)|すべて)(?:が|の).{0,24}?(?:通|成功).{0,12}?(?:のみ|だけ)?(?:完了|終了)"
)


def _clause_has_condition_scope(
    clause_id: str | None,
    operators: list[ScopeOperator],
) -> bool:
    if clause_id is None:
        return False
    return any(
        item.clause_id == clause_id and item.operator_type == "condition"
        for item in operators
    )


def _drop_conditional_connection_propositions(
    propositions: list[Proposition],
    operators: list[ScopeOperator],
) -> list[Proposition]:
    output: list[Proposition] = []
    for item in propositions:
        if (
            item.intent_type == "condition"
            and item.predicate == "条件とする"
            and _clause_has_condition_scope(item.clause_id, operators)
        ):
            bound_action = any(
                other.clause_id == item.clause_id
                and other.intent_type in {
                    "action",
                    "modify",
                    "remove",
                    "prohibition",
                }
                for other in propositions
                if other is not item
            )
            if bound_action:
                output.append(item)
                continue
            continue
        output.append(item)
    return output


def _rewrite_generic_request_propositions(
    propositions: list[Proposition],
    frame_by_clause: dict[str, list[PredicateFrame]],
) -> list[Proposition]:
    updated: list[Proposition] = []
    for item in propositions:
        if (
            item.intent_type == "request"
            and item.predicate == "要求する"
            and item.clause_id
        ):
            if any(
                other.clause_id == item.clause_id
                and other.intent_type in {"action", "modify", "remove"}
                for other in propositions
                if other is not item
            ):
                updated.append(item)
                continue
            frames = frame_by_clause.get(item.clause_id, [])
            main = _primary_predicate_frame(frames) if frames else None
            if main is not None and main.predicate not in {"要求する", "下さる"}:
                updated.append(item.model_copy(update={
                    "intent_type": "observation",
                    "predicate": main.predicate,
                    "surface_predicate": main.surface_predicate,
                    "arguments": main.arguments or item.arguments,
                    "speech_act": "request",
                    "executable_candidate": False,
                    "source_span": main.source_span,
                    "evidence_ids": list(dict.fromkeys([
                        *item.evidence_ids,
                        "READING:PREDICATE_FRAME",
                    ])),
                }))
                continue
        updated.append(item)
    return updated


def _ensure_completion_criteria_propositions(
    propositions: list[Proposition],
    clauses: list[Clause],
    original_text: str,
    operators: list[ScopeOperator],
) -> list[Proposition]:
    if any(item.intent_type == "completion_criteria" for item in propositions):
        return [
            item
            for item in propositions
            if not (
                item.intent_type == "observation"
                and item.predicate == "持つ"
                and _COMPLETION_WITH_HOLDING_RE.search(original_text)
            )
        ]
    patterns = (
        _COMPLETION_WITH_HOLDING_RE,
        _COMPLETION_ONLY_RE,
        _COMPLETION_CRITERIA_NOMINAL_RE,
    )
    if not any(item.search(original_text) for item in patterns):
        return propositions
    clause = clauses[0] if clauses else None
    proposition = Proposition(
        proposition_id=f"P-{len(propositions) + 1:03d}",
        predicate="完了条件とする",
        surface_predicate=original_text.strip(),
        intent_type="completion_criteria",
        value=original_text.strip(),
        polarity="positive",
        sentence_mood="declarative",
        speech_act="assertion",
        epistemic_status="asserted",
        executable_candidate=False,
        clause_id=clause.clause_id if clause else None,
        source_span=clause.source_span if clause else _span(0, len(original_text), original_text),
        evidence_ids=["READING:COMPLETION_CRITERIA"],
        inference_sources=["deterministic-reading-runtime"],
    )
    return [*propositions, proposition]


def _dedupe_propositions(propositions: list[Proposition]) -> list[Proposition]:
    seen: set[tuple[str | None, str, str]] = set()
    output: list[Proposition] = []
    for item in propositions:
        key = (item.clause_id, item.intent_type, item.predicate)
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _prune_redundant_observations(
    propositions: list[Proposition],
) -> list[Proposition]:
    by_clause: dict[str | None, list[Proposition]] = {}
    for item in propositions:
        by_clause.setdefault(item.clause_id, []).append(item)

    output: list[Proposition] = []
    for item in propositions:
        peers = by_clause.get(item.clause_id, [])
        peer_predicates = {peer.predicate for peer in peers}
        if item.intent_type == "observation":
            if any(peer.intent_type == "prohibition" for peer in peers):
                if item.predicate in {"余計", "為る", "する"}:
                    continue
            if "終了する" in peer_predicates and item.predicate in {
                "不要",
                "完了する",
            }:
                continue
        output.append(item)
    return output


def _normalize_concessive_and_contrast_propositions(
    propositions: list[Proposition],
    *,
    original_text: str,
    operators: list[ScopeOperator],
    discourse: list[DiscourseRelation],
) -> list[Proposition]:
    has_concessive = any(
        item.operator_type == "condition"
        and item.semantic_value == "concessive_condition"
        and item.marker == "にもかかわらず"
        for item in operators
    )
    has_tadashi = any(
        item.marker == "ただし" and item.relation == "contrasts_with"
        for item in discourse
    )
    filtered = list(propositions)
    if has_concessive:
        filtered = [
            item
            for item in filtered
            if not (
                item.intent_type == "action"
                and item.predicate == "実行する"
                and "公開" in original_text
            )
        ]
        filtered = [
            item
            for item in filtered
            if item.predicate != "関わる"
        ]
    if has_tadashi:
        filtered = [
            item
            for item in filtered
            if item.intent_type != "exception"
        ]
    return filtered


def _ensure_observations_for_predicate_frames(
    propositions: list[Proposition],
    clauses: list[Clause],
    frame_by_clause: dict[str, list[PredicateFrame]],
    operators: list[ScopeOperator],
) -> list[Proposition]:
    updated = list(propositions)
    for clause in clauses:
        clause_conditions = [
            item
            for item in operators
            if item.clause_id == clause.clause_id
            and item.operator_type == "condition"
        ]
        if any(
            item.clause_id == clause.clause_id
            and item.intent_type == "action"
            for item in updated
        ) and clause_conditions and not any(
            item.semantic_value == "concessive_condition"
            for item in clause_conditions
        ):
            continue
        clause_frames = [
            frame
            for frame in _substantive_predicate_frames(
                frame_by_clause.get(clause.clause_id, [])
            )
            if frame.predicate not in {
                "関わる",
                "不要",
                "余計",
                "為る",
            }
        ]
        if not clause_frames:
            continue
        covered = {
            item.predicate
            for item in updated
            if item.clause_id == clause.clause_id
            and item.intent_type in {"observation", "request", "prohibition"}
        }
        for frame in clause_frames:
            if frame.predicate in covered:
                continue
            updated.append(Proposition(
                proposition_id=f"P-{len(updated) + 1:03d}",
                predicate=frame.predicate,
                surface_predicate=frame.surface_predicate,
                intent_type="observation",
                value=clause.text,
                polarity=frame.polarity,
                sentence_mood=(
                    "interrogative"
                    if re.search(r"[？?]|(?:でしょう|だろう)か", clause.text)
                    else "declarative"
                ),
                speech_act=(
                    "question"
                    if re.search(r"[？?]|(?:でしょう|だろう)か", clause.text)
                    else "assertion"
                ),
                epistemic_status="asserted",
                executable_candidate=False,
                clause_id=clause.clause_id,
                source_span=frame.source_span,
                evidence_ids=["READING:PREDICATE_FRAME"],
                inference_sources=["deterministic-reading-runtime"],
            ))
            covered.add(frame.predicate)
    return updated


def _drop_spurious_preserve_propositions(
    propositions: list[Proposition],
    frame_by_clause: dict[str, list[PredicateFrame]],
    *,
    original_text: str,
    operators: list[ScopeOperator],
) -> list[Proposition]:
    if not re.search(r"(?:ても|でも|にもかかわらず)", original_text):
        return propositions
    if not any(
        item.operator_type == "condition"
        and item.semantic_value == "concessive_condition"
        for item in operators
    ):
        return propositions
    output: list[Proposition] = []
    for item in propositions:
        if item.intent_type != "preserve":
            output.append(item)
            continue
        frames = frame_by_clause.get(item.clause_id or "", [])
        if not frames:
            continue
        main = _primary_predicate_frame(frames)
        if main.predicate in {"残す", "残る", "維持する", "保つ"}:
            output.append(item)
            continue
        continue
    return output


def _rewrite_gratitude_with_incomplete_tail(
    propositions: list[Proposition],
    original_text: str,
    frame_by_clause: dict[str, list[PredicateFrame]],
) -> list[Proposition]:
    if not _GRATITUDE_RE.search(original_text):
        return propositions
    if not re.search(r"まだ.{0,12}?(?:終わ|完了)", original_text):
        return propositions
    filtered = [
        item
        for item in propositions
        if item.intent_type != "exception"
    ]
    if not any(item.predicate == "感謝する" for item in filtered):
        filtered = _ensure_gratitude_proposition(filtered, [], original_text)
    for clause_id, frames in frame_by_clause.items():
        main = _primary_predicate_frame(frames) if frames else None
        if main is None:
            continue
        if any(
            item.clause_id == clause_id
            and item.predicate == main.predicate
            for item in filtered
        ):
            continue
        if main.predicate in {"感謝する", "下さる"}:
            continue
        filtered.append(Proposition(
            proposition_id=f"P-{len(filtered) + 1:03d}",
            predicate=main.predicate,
            surface_predicate=main.surface_predicate,
            intent_type="observation",
            value=original_text,
            polarity=main.polarity,
            sentence_mood="declarative",
            speech_act="assertion",
            epistemic_status="asserted",
            executable_candidate=False,
            clause_id=clause_id,
            source_span=main.source_span,
            evidence_ids=["READING:INCOMPLETE_TAIL"],
            inference_sources=["deterministic-reading-runtime"],
        ))
    return filtered


def _predicate_bounds(
    head_index: int,
    clause_indices: list[int],
    tokens: list[Token],
) -> tuple[int, int, str, str]:
    position = clause_indices.index(head_index)
    start_position = position
    head = tokens[head_index]
    if position and (
        head.normalized in {"為る", "する"} or head.surface.startswith("し")
    ):
        previous = tokens[clause_indices[position - 1]]
        if _pos0(previous) == "名詞":
            start_position -= 1

    end_position = position
    cursor = position + 1
    while cursor < len(clause_indices):
        token = tokens[clause_indices[cursor]]
        previous = tokens[clause_indices[cursor - 1]]
        if _pos0(token) == "助動詞" or token.surface in {"て", "で"}:
            end_position = cursor
            cursor += 1
            continue
        if (
            token.normalized in _ASPECT_AUXILIARIES
            and previous.surface in {"て", "で"}
        ):
            end_position = cursor
            cursor += 1
            continue
        if token.surface in _COPULAS:
            end_position = cursor
            cursor += 1
            continue
        if token.surface.rstrip("。！？!?") in _POLITE_REQUEST_TAIL_SURFACES:
            end_position = cursor
            cursor += 1
            continue
        break

    selected = clause_indices[start_position:end_position + 1]
    start = tokens[selected[0]].span.start
    end = tokens[selected[-1]].span.end
    surface = "".join(tokens[index].surface for index in selected)
    if start_position < position:
        predicate = tokens[selected[0]].normalized + "する"
    else:
        predicate = head.normalized or head.surface
    return start, end, predicate, surface


def _arguments_before(
    indices: list[int],
    tokens: list[Token],
    original: str,
) -> list[tuple[Argument, int]]:
    output: list[tuple[Argument, int]] = []
    buffer: list[int] = []
    for position, index in enumerate(indices):
        token = tokens[index]
        if _is_punctuation(token):
            buffer = []
            continue
        role = _CASE_ROLES.get(token.surface)
        marker = token.surface
        next_token = (
            tokens[indices[position + 1]]
            if position + 1 < len(indices)
            else None
        )
        following_token = (
            tokens[indices[position + 2]]
            if position + 2 < len(indices)
            else None
        )
        if token.surface == "に" and next_token is not None:
            if next_token.surface in {"よって", "因って", "依って"}:
                role = "agent"
                marker = "によって"
            elif next_token.normalized in {"よる", "因る", "依る"} and (
                following_token is not None and following_token.surface == "て"
            ):
                role = "agent"
                marker = "によって"
        if role is None:
            if _pos0(token) not in {"助詞", "助動詞"}:
                buffer.append(index)
            continue
        if not buffer:
            continue
        start_index = buffer[0]
        end_index = buffer[-1]
        start = tokens[start_index].span.start
        end = tokens[end_index].span.end
        value = original[start:end].strip()
        if value:
            output.append((Argument(
                role=role,
                value=value,
                case_marker=marker,
                explicit=True,
                span=_span(start, end, original),
            ), end_index))
        buffer = []
    return output


def _tense(text: str) -> str:
    if re.search(
        r"(?:た|だ|だった|でした|ました)(?:らしい|そうだ|とのことだ?)?[。！？!?]?$",
        text,
    ):
        return "past"
    return "nonpast"


def _aspect(text: str) -> list[str]:
    patterns = (
        (r"ている", "progressive_or_state"),
        (r"てある", "resultant_state"),
        (r"ておく", "preparatory"),
        (r"てしまう", "completion_or_regret"),
        (r"てみる", "attempt"),
        (r"てくる", "change_toward_reference"),
        (r"ていく", "change_away_from_reference"),
        (r"始める", "inchoative"),
        (r"続ける", "continuative"),
        (r"終わる", "terminative"),
    )
    return [value for pattern, value in patterns if re.search(pattern, text)]


def _voice(text: str) -> list[str]:
    if re.search(r"(?:させられる|せられる)", text):
        return ["causative_passive"]
    if re.search(r"(?:させる|せる)", text):
        return ["causative"]
    if re.search(r"(?:された|される|されて|られた|られる|られて)", text):
        return ["passive"]
    if re.search(r"(?:られる|れる)", text):
        return ["passive_or_potential"]
    if re.search(r"(?:できる|可能だ|可能です)", text):
        return ["potential"]
    return ["active"]


def _has_passive_voice(voice: list[str]) -> bool:
    return any(
        value in {"passive", "passive_or_potential", "causative_passive"}
        for value in voice
    )


def _arguments_for_voice(
    arguments: list[Argument],
    voice: list[str],
) -> list[Argument]:
    if not _has_passive_voice(voice):
        return arguments
    updated: list[Argument] = []
    for argument in arguments:
        if argument.case_marker == "によって":
            updated.append(argument.model_copy(update={"role": "agent"}))
            continue
        if (
            argument.role in {"agent", "topic"}
            and argument.case_marker in {"が", "は"}
        ):
            updated.append(argument.model_copy(update={"role": "patient"}))
            continue
        updated.append(argument)
    return updated


def _modalities(text: str) -> list[str]:
    values: list[str] = []
    polite_ranges = _polite_request_ranges(text)
    for pattern, value in _MODALITY_PATTERNS:
        for match in pattern.finditer(text):
            if value == "inference" and _inside_ranges(match, polite_ranges):
                continue
            if value not in values:
                values.append(value)
    return values


def _polite_request_ranges(text: str) -> list[tuple[int, int]]:
    return [match.span() for match in _POLITE_REQUEST.finditer(text)]


def _inside_ranges(
    match: re.Match[str],
    ranges: list[tuple[int, int]],
) -> bool:
    start, end = match.span()
    return any(left <= start and end <= right for left, right in ranges)


def _has_semantic_negation(text: str) -> bool:
    polite_ranges = _polite_request_ranges(text)
    return any(
        not _inside_ranges(match, polite_ranges)
        for pattern, _ in _NEGATION_PATTERNS
        for match in pattern.finditer(text)
    )


def _scope_target_frame_ids(
    operator_type: str,
    start: int,
    end: int,
    frames: list[PredicateFrame],
) -> list[str]:
    ordered = sorted(frames, key=lambda item: item.source_span.start)
    if not ordered:
        return []

    if operator_type == "condition":
        following = [
            frame for frame in ordered if frame.source_span.start >= end
        ]
        return [following[0].frame_id] if following else []

    if operator_type == "question":
        return [ordered[-1].frame_id]

    if operator_type == "quantifier":
        following = [
            frame for frame in ordered if frame.source_span.start >= end
        ]
        if following:
            return [following[0].frame_id]

    overlapping = [
        frame
        for frame in ordered
        if frame.source_span.start < end and start < frame.source_span.end
    ]
    if overlapping:
        return [overlapping[-1].frame_id]

    preceding = [
        frame for frame in ordered if frame.source_span.start < end
    ]
    if preceding:
        return [preceding[-1].frame_id]

    following = [
        frame for frame in ordered if frame.source_span.start >= end
    ]
    return [following[0].frame_id] if following else []


def _operators_for_clause(
    clause: Clause,
    original: str,
    frames: list[PredicateFrame],
    start_number: int,
) -> tuple[list[ScopeOperator], list[dict]]:
    output: list[ScopeOperator] = []
    unresolved: list[dict] = []
    used: dict[str, list[tuple[int, int]]] = {}
    polite_ranges = _polite_request_ranges(clause.text)

    def add(
        operator_type: str,
        semantic_value: str,
        match: re.Match[str],
    ) -> None:
        relative_start, relative_end = match.span()
        start = clause.source_span.start + relative_start
        end = clause.source_span.start + relative_end
        if any(
            left < relative_end and relative_start < right
            for left, right in used.setdefault(operator_type, [])
        ):
            return
        used[operator_type].append((relative_start, relative_end))
        targets = _scope_target_frame_ids(
            operator_type,
            start,
            end,
            frames,
        )
        operands = [clause.source_span]
        if operator_type == "condition":
            operands = [
                _span(clause.source_span.start, end, original),
                _span(end, clause.source_span.end, original),
            ]
        if operator_type == "question" and not targets:
            return
        if operator_type == "condition" and not targets:
            consequent = operands[-1].source_text if len(operands) > 1 else ""
            status = (
                ItemStatus.RESOLVED
                if re.search(
                    r"(?:完了|終了|成功|可|不可)(?:。|、|$|ではない)",
                    consequent,
                )
                or (
                    semantic_value == "general_condition"
                    and match.group(0) == "限り"
                    and re.search(r"完了|終了", consequent)
                )
                else ItemStatus.AMBIGUOUS
            )
        else:
            status = ItemStatus.RESOLVED if targets else ItemStatus.AMBIGUOUS
        operator_id = f"SO-{start_number + len(output):03d}"
        output.append(ScopeOperator(
            operator_id=operator_id,
            clause_id=clause.clause_id,
            operator_type=operator_type,
            semantic_value=semantic_value,
            marker=match.group(0),
            source_span=_span(start, end, original),
            operand_spans=operands,
            target_frame_ids=targets,
            status=status,
        ))
        if status != ItemStatus.RESOLVED:
            unresolved.append({
                "type": "reading_scope_target",
                "operator_id": operator_id,
                "status": status.value,
                "source_span": _span(start, end, original).model_dump(),
            })

    for pattern, value in _NEGATION_PATTERNS:
        for match in pattern.finditer(clause.text):
            if _inside_ranges(match, polite_ranges):
                continue
            add("negation", value, match)
    for pattern, value in _CONDITION_PATTERNS:
        for match in pattern.finditer(clause.text):
            if match.group(0) in {"ても", "でも"} and _inside_ranges(
                match,
                polite_ranges,
            ):
                continue
            add("condition", value, match)
    for pattern, value in _MODALITY_PATTERNS:
        for match in pattern.finditer(clause.text):
            if value == "inference" and _inside_ranges(match, polite_ranges):
                continue
            if (
                value == "inference"
                and match.group(0) in {"でしょう", "だろう"}
                and re.search(r"(?:でしょう|だろう)か[。！？!?]?$", clause.text)
            ):
                continue
            add("modality", value, match)
    for pattern, value in _QUANTIFIER_PATTERNS:
        for match in pattern.finditer(clause.text):
            add("quantifier", value, match)
    if re.search(
        r"[？?]|(?:の|ん|だ|です|ます)?か[。！？!?]?$|(?:でしょう|だろう)か[。！？!?]?$",
        clause.text,
    ):
        match = re.search(
            r"[？?]|(?:でしょう|だろう)か|か(?=[。！？!?]?$)",
            clause.text,
        )
        if match:
            add("question", "interrogative", match)
    return output, unresolved


def _discourse_relations(clauses: list[Clause]) -> list[DiscourseRelation]:
    output: list[DiscourseRelation] = []
    ordered = sorted(clauses, key=lambda item: item.source_span.start)
    for previous, current in zip(ordered, ordered[1:]):
        stripped = current.text.lstrip()
        previous_stripped = previous.text.rstrip(" \t\r\n、。！？!?")
        matched = False
        for pattern, relation in _PREVIOUS_TAIL_DISCOURSE_MARKERS:
            match = pattern.search(previous_stripped)
            if not match:
                continue
            output.append(DiscourseRelation(
                relation_id=f"DR-{len(output) + 1:03d}",
                source_clause_id=previous.clause_id,
                target_clause_id=current.clause_id,
                relation=relation,
                marker=match.group(0),
                confidence=0.98,
            ))
            matched = True
            break
        if matched:
            continue
        for pattern, relation in _DISCOURSE_MARKERS:
            match = pattern.search(stripped)
            if not match:
                continue
            output.append(DiscourseRelation(
                relation_id=f"DR-{len(output) + 1:03d}",
                source_clause_id=previous.clause_id,
                target_clause_id=current.clause_id,
                relation=relation,
                marker=match.group(0),
                confidence=0.98,
            ))
            break
    return output


def _attributions(
    original: str,
    clauses: list[Clause],
    frames: list[PredicateFrame],
) -> list[AttributionFrame]:
    output: list[AttributionFrame] = []
    for start, end, _ in quote_ranges(original):
        clause = next(
            (
                item
                for item in clauses
                if item.source_span.start <= start < item.source_span.end
            ),
            None,
        )
        if clause is None:
            continue
        tail = original[end:clause.source_span.end]
        report = re.search(
            r"と(?:(?P<source>[^、。！？!?]{1,24}?)(?:が|は))?"
            r"(?P<predicate>言った|述べた|報告した|説明した|書いた|記載した)",
            tail,
        )
        source = report.group("source").strip() if report and report.group("source") else None
        source_span = None
        reporting_predicate = report.group("predicate") if report else None
        if source and report:
            source_start = end + report.start("source")
            source_span = _span(source_start, source_start + len(source), original)
        output.append(AttributionFrame(
            attribution_id=f"AT-{len(output) + 1:03d}",
            clause_id=clause.clause_id,
            attribution_type="quotation",
            content_span=_span(start, end, original),
            source=source,
            source_span=source_span,
            reporting_predicate=reporting_predicate,
            related_frame_ids=[
                item.frame_id
                for item in frames
                if start <= item.source_span.start and item.source_span.end <= end
            ],
            status=(
                ItemStatus.RESOLVED
                if report is not None
                else ItemStatus.INSUFFICIENT
            ),
        ))

    for clause in clauses:
        source_match = re.search(
            r"(?P<source>[^、。！？!?]{1,24}?)(?:によると|によれば)",
            clause.text,
        )
        if not source_match:
            continue
        source = source_match.group("source").strip()
        source_start = clause.source_span.start + source_match.start("source")
        output.append(AttributionFrame(
            attribution_id=f"AT-{len(output) + 1:03d}",
            clause_id=clause.clause_id,
            attribution_type="hearsay",
            content_span=clause.source_span,
            source=source,
            source_span=_span(source_start, source_start + len(source), original),
            reporting_predicate="伝聞",
            related_frame_ids=[
                item.frame_id for item in frames if item.clause_id == clause.clause_id
            ],
        ))
    return output


class DeterministicReadingRuntime:
    """Create sentence-reading structures without generative inference.

    The runtime describes predicate/argument, scope, and discourse evidence.
    It never converts an ordinary statement into an executable instruction.
    """

    def __init__(self, *, max_frames: int = 256, max_operators: int = 512):
        self.max_frames = max_frames
        self.max_operators = max_operators
        self.last_metrics: dict[str, int | float] = {}

    @staticmethod
    def _detect_paragraphs(
        original_text: str,
        clauses: list[Clause],
    ) -> ParagraphStructure:
        """Detect only explicitly separated paragraphs and preserve source spans."""
        boundaries = list(_PARAGRAPH_BOUNDARY.finditer(original_text))
        if not boundaries:
            return ParagraphStructure(
                ambiguity_flag=True,
                unresolved=[{
                    "type": "paragraph_boundary_not_explicit",
                    "status": ItemStatus.AMBIGUOUS.value,
                }],
                status=ItemStatus.AMBIGUOUS,
            )

        paragraph_spans: list[tuple[int, int]] = []
        cursor = 0
        for boundary in boundaries:
            start = cursor
            end = boundary.start()
            while start < end and original_text[start].isspace():
                start += 1
            while end > start and original_text[end - 1].isspace():
                end -= 1
            if start < end:
                paragraph_spans.append((start, end))
            cursor = boundary.end()

        start = cursor
        end = len(original_text)
        while start < end and original_text[start].isspace():
            start += 1
        while end > start and original_text[end - 1].isspace():
            end -= 1
        if start < end:
            paragraph_spans.append((start, end))

        paragraphs: list[ParagraphFrame] = []
        unresolved: list[dict] = []
        for start, end in paragraph_spans:
            sentence_clauses = [
                clause
                for clause in clauses
                if start <= clause.source_span.start
                and clause.source_span.end <= end
            ]
            overlapping = [
                clause
                for clause in clauses
                if clause.source_span.start < end
                and start < clause.source_span.end
                and clause not in sentence_clauses
            ]
            if overlapping:
                unresolved.append({
                    "type": "paragraph_boundary_overlap",
                    "paragraph_start": start,
                    "paragraph_end": end,
                    "clause_ids": [item.clause_id for item in overlapping],
                    "status": ItemStatus.AMBIGUOUS.value,
                })
            if not sentence_clauses:
                unresolved.append({
                    "type": "paragraph_without_sentence",
                    "paragraph_start": start,
                    "paragraph_end": end,
                    "status": ItemStatus.INSUFFICIENT.value,
                })
                continue

            topic = sentence_clauses[0].source_span
            paragraphs.append(ParagraphFrame(
                paragraph_id=f"PG-{len(paragraphs) + 1:03d}",
                text=original_text[start:end],
                start_char=start,
                end_char=end,
                source_span=_span(start, end, original_text),
                clause_ids=[item.clause_id for item in sentence_clauses],
                proposition_ids=list(dict.fromkeys(
                    proposition_id
                    for item in sentence_clauses
                    for proposition_id in item.proposition_ids
                )),
                sentence_spans=[item.source_span for item in sentence_clauses],
                topic_sentence=topic.source_text,
                topic_sentence_start=topic.start,
                topic_sentence_end=topic.end,
                topic_sentence_span=topic,
            ))

        status = (
            ItemStatus.RESOLVED
            if paragraphs and not unresolved
            else ItemStatus.AMBIGUOUS
        )
        return ParagraphStructure(
            paragraphs=paragraphs,
            relations=[],
            boundary_method="explicit_blank_line",
            ambiguity_flag=bool(unresolved or not paragraphs),
            unresolved=unresolved,
            status=status,
        )

    def _extract_summary(
        self,
        paragraph_structure: ParagraphStructure | None,
    ) -> SummaryResult:
        """Extract a deterministic document summary from paragraph topics."""
        if (
            paragraph_structure is None
            or paragraph_structure.ambiguity_flag
            or not paragraph_structure.paragraphs
        ):
            return SummaryResult(
                status="AMBIGUOUS",
                candidates=[],
                confidence=0.0,
            )

        paragraphs = paragraph_structure.paragraphs
        topics: list[dict[str, str | int | float]] = []
        last_index = len(paragraphs) - 1
        for idx, para in enumerate(paragraphs):
            if not para.topic_sentence:
                continue
            if len(paragraphs) == 1 or idx == 0:
                weight = 1.0
            elif idx == last_index:
                weight = 0.75
            else:
                weight = 0.5
            score = max(0.0, min(weight * para.confidence, 1.0))
            topics.append({
                "text": para.topic_sentence,
                "index": idx,
                "score": score,
            })

        if not topics:
            return SummaryResult(
                status="AMBIGUOUS",
                candidates=[],
                confidence=0.0,
            )

        sorted_topics = sorted(
            topics,
            key=lambda item: (-float(item["score"]), int(item["index"])),
        )
        best = sorted_topics[0]

        if len(sorted_topics) >= 2:
            diff = float(best["score"]) - float(sorted_topics[1]["score"])
            if diff < 0.2:
                selected = sorted_topics[:3]
                return SummaryResult(
                    status="AMBIGUOUS",
                    candidates=[str(item["text"]) for item in selected],
                    confidence=max(0.0, min(diff + 0.5, 1.0)),
                    source_paragraph_indices=[
                        int(item["index"]) for item in selected
                    ],
                    method="topic_sentence_aggregation",
                )

        return SummaryResult(
            summary_text=str(best["text"]),
            confidence=max(0.0, min(float(best["score"]) + 0.5, 1.0)),
            status="DETERMINED",
            candidates=[],
            source_paragraph_indices=[int(best["index"])],
            method="topic_sentence_aggregation",
        )

    @staticmethod
    def _extract_argumentation(
        *,
        paragraph_structure: ParagraphStructure | None,
        summary: SummaryResult | None,
        clauses: list[Clause],
        discourse_relations: list[DiscourseRelation],
        scope_operators: list[ScopeOperator],
        attribution_frames: list[AttributionFrame],
    ) -> ArgumentationResult:
        """Build only argument relations supported by existing reading evidence."""
        clause_by_id = {item.clause_id: item for item in clauses}
        paragraph_by_clause: dict[str, ParagraphFrame] = {}
        paragraphs = (
            paragraph_structure.paragraphs
            if paragraph_structure is not None
            else []
        )
        for paragraph in paragraphs:
            for clause_id in paragraph.clause_ids:
                paragraph_by_clause[clause_id] = paragraph

        buckets: dict[str, list[ArgumentComponent]] = {
            "claim": [],
            "reason": [],
            "evidence": [],
            "explicit_premise": [],
            "implicit_premise": [],
            "counterargument": [],
            "rebuttal": [],
            "limitation": [],
        }
        prefixes = {
            "claim": "C",
            "reason": "R",
            "evidence": "E",
            "explicit_premise": "EP",
            "implicit_premise": "IP",
            "counterargument": "CA",
            "rebuttal": "RB",
            "limitation": "L",
        }
        component_index: dict[tuple, ArgumentComponent] = {}
        edges: list[ArgumentEdge] = []
        unresolved: list[dict] = []
        support_relation_by_edge: dict[str, str] = {}

        def add_component(
            component_type: str,
            *,
            text: str | None,
            clause_id: str | None = None,
            paragraph_id: str | None = None,
            source_span: OriginalSpan | None = None,
            evidence_ids: list[str] | None = None,
            related_component_ids: list[str] | None = None,
            status: str = "DETERMINED",
            confidence: float = 0.98,
        ) -> ArgumentComponent:
            key = (
                component_type,
                clause_id,
                paragraph_id,
                text,
                source_span.start if source_span else None,
                source_span.end if source_span else None,
            )
            existing = component_index.get(key)
            if existing is not None:
                merged_evidence = list(dict.fromkeys([
                    *existing.evidence_ids,
                    *(evidence_ids or []),
                ]))
                merged_related = list(dict.fromkeys([
                    *existing.related_component_ids,
                    *(related_component_ids or []),
                ]))
                updated = existing.model_copy(update={
                    "evidence_ids": merged_evidence,
                    "related_component_ids": merged_related,
                    "confidence": max(existing.confidence, confidence),
                })
                position = buckets[component_type].index(existing)
                buckets[component_type][position] = updated
                component_index[key] = updated
                return updated
            component = ArgumentComponent(
                component_id=(
                    f"ARG-{prefixes[component_type]}-"
                    f"{len(buckets[component_type]) + 1:03d}"
                ),
                component_type=component_type,
                text=text,
                clause_id=clause_id,
                paragraph_id=paragraph_id,
                source_span=source_span,
                evidence_ids=list(evidence_ids or []),
                related_component_ids=list(related_component_ids or []),
                status=status,
                confidence=confidence,
            )
            buckets[component_type].append(component)
            component_index[key] = component
            return component

        def paragraph_id_for(clause_id: str | None) -> str | None:
            if clause_id is None:
                return None
            paragraph = paragraph_by_clause.get(clause_id)
            return paragraph.paragraph_id if paragraph else None

        def component_for_clause(
            component_type: str,
            clause_id: str,
        ) -> ArgumentComponent | None:
            return next(
                (
                    item
                    for item in buckets[component_type]
                    if item.clause_id == clause_id
                ),
                None,
            )

        def ensure_claim(
            clause_id: str,
            evidence_id: str,
            confidence: float,
        ) -> ArgumentComponent | None:
            existing = component_for_clause("claim", clause_id)
            if existing is not None:
                return existing
            clause = clause_by_id.get(clause_id)
            if clause is None:
                unresolved.append({
                    "type": "argumentation_missing_clause",
                    "clause_id": clause_id,
                    "evidence_id": evidence_id,
                })
                return None
            return add_component(
                "claim",
                text=clause.text,
                clause_id=clause_id,
                paragraph_id=paragraph_id_for(clause_id),
                source_span=clause.source_span,
                evidence_ids=[evidence_id],
                confidence=confidence,
            )

        def add_clause_component(
            component_type: str,
            clause_id: str,
            evidence_id: str,
            confidence: float,
        ) -> ArgumentComponent | None:
            clause = clause_by_id.get(clause_id)
            if clause is None:
                unresolved.append({
                    "type": "argumentation_missing_clause",
                    "clause_id": clause_id,
                    "evidence_id": evidence_id,
                })
                return None
            return add_component(
                component_type,
                text=clause.text,
                clause_id=clause_id,
                paragraph_id=paragraph_id_for(clause_id),
                source_span=clause.source_span,
                evidence_ids=[evidence_id],
                confidence=confidence,
            )

        def add_edge(
            source: ArgumentComponent,
            target: ArgumentComponent,
            relation: str,
            evidence_id: str,
            confidence: float,
        ) -> ArgumentEdge:
            existing = next(
                (
                    item
                    for item in edges
                    if item.source_component_id == source.component_id
                    and item.target_component_id == target.component_id
                    and item.relation == relation
                ),
                None,
            )
            if existing is not None:
                return existing
            edge = ArgumentEdge(
                edge_id=f"ARG-E-{len(edges) + 1:03d}",
                source_component_id=source.component_id,
                target_component_id=target.component_id,
                relation=relation,
                evidence_ids=[evidence_id],
                confidence=confidence,
            )
            edges.append(edge)
            return edge

        if (
            paragraph_structure is None
            or paragraph_structure.ambiguity_flag
            or paragraph_structure.status != ItemStatus.RESOLVED
        ):
            unresolved.append({
                "type": "argumentation_paragraph_structure_ambiguous",
                "status": "AMBIGUOUS",
            })

        if summary is None or summary.status != "DETERMINED" or not summary.summary_text:
            unresolved.append({
                "type": "argumentation_summary_ambiguous",
                "status": "AMBIGUOUS",
            })
            if summary is not None:
                for index, candidate_text in enumerate(summary.candidates or []):
                    paragraph_index = (
                        summary.source_paragraph_indices[index]
                        if index < len(summary.source_paragraph_indices)
                        else None
                    )
                    paragraph = (
                        paragraphs[paragraph_index]
                        if paragraph_index is not None
                        and 0 <= paragraph_index < len(paragraphs)
                        else None
                    )
                    clause_id = paragraph.clause_ids[0] if paragraph and paragraph.clause_ids else None
                    clause = clause_by_id.get(clause_id) if clause_id else None
                    add_component(
                        "claim",
                        text=candidate_text,
                        clause_id=clause_id,
                        paragraph_id=paragraph.paragraph_id if paragraph else None,
                        source_span=(
                            paragraph.topic_sentence_span
                            if paragraph and paragraph.topic_sentence_span
                            else clause.source_span if clause else None
                        ),
                        evidence_ids=["SUMMARY:CANDIDATE"],
                        status="AMBIGUOUS",
                        confidence=summary.confidence,
                    )
        else:
            source_indices = summary.source_paragraph_indices or [0]
            for index in source_indices:
                if not 0 <= index < len(paragraphs):
                    unresolved.append({
                        "type": "argumentation_summary_source_missing",
                        "paragraph_index": index,
                        "status": "AMBIGUOUS",
                    })
                    continue
                paragraph = paragraphs[index]
                topic_span = paragraph.topic_sentence_span or paragraph.source_span
                clause = next(
                    (
                        item
                        for item in clauses
                        if item.source_span.start <= topic_span.start
                        and topic_span.end <= item.source_span.end
                    ),
                    None,
                )
                add_component(
                    "claim",
                    text=summary.summary_text,
                    clause_id=clause.clause_id if clause else None,
                    paragraph_id=paragraph.paragraph_id,
                    source_span=topic_span,
                    evidence_ids=["SUMMARY:DETERMINED"],
                    confidence=summary.confidence,
                )

        for relation in discourse_relations:
            if relation.status != ItemStatus.RESOLVED:
                unresolved.append({
                    "type": "argumentation_discourse_relation_ambiguous",
                    "discourse_relation_id": relation.relation_id,
                    "status": "AMBIGUOUS",
                })
                continue
            evidence_id = f"DISCOURSE:{relation.relation_id}"
            confidence = relation.confidence
            if relation.relation == "justifies":
                claim = ensure_claim(
                    relation.source_clause_id,
                    evidence_id,
                    confidence,
                )
                reason = add_clause_component(
                    "reason",
                    relation.target_clause_id,
                    evidence_id,
                    confidence,
                )
                if claim and reason:
                    edge = add_edge(
                        reason,
                        claim,
                        "supports",
                        evidence_id,
                        confidence,
                    )
                    support_relation_by_edge[edge.edge_id] = relation.relation
            elif relation.relation in {"concludes", "causes"}:
                claim = ensure_claim(
                    relation.target_clause_id,
                    evidence_id,
                    confidence,
                )
                reason = add_clause_component(
                    "reason",
                    relation.source_clause_id,
                    evidence_id,
                    confidence,
                )
                if claim and reason:
                    edge = add_edge(
                        reason,
                        claim,
                        "supports",
                        evidence_id,
                        confidence,
                    )
                    support_relation_by_edge[edge.edge_id] = relation.relation
            elif relation.relation == "exemplifies":
                claim = ensure_claim(
                    relation.source_clause_id,
                    evidence_id,
                    confidence,
                )
                evidence = add_clause_component(
                    "evidence",
                    relation.target_clause_id,
                    evidence_id,
                    confidence,
                )
                if claim and evidence:
                    add_edge(
                        evidence,
                        claim,
                        "supports",
                        evidence_id,
                        confidence,
                    )
            elif relation.relation == "contrasts_with":
                limitation_marker = relation.marker in {"ただし", "もっとも"}
                source_counter = component_for_clause(
                    "counterargument",
                    relation.source_clause_id,
                )
                if source_counter is not None and not limitation_marker:
                    rebuttal = add_clause_component(
                        "rebuttal",
                        relation.target_clause_id,
                        evidence_id,
                        confidence,
                    )
                    if rebuttal:
                        add_edge(
                            rebuttal,
                            source_counter,
                            "opposes",
                            evidence_id,
                            confidence,
                        )
                    continue
                claim = ensure_claim(
                    relation.source_clause_id,
                    evidence_id,
                    confidence,
                )
                target_type = "limitation" if limitation_marker else "counterargument"
                target = add_clause_component(
                    target_type,
                    relation.target_clause_id,
                    evidence_id,
                    confidence,
                )
                if claim and target:
                    add_edge(
                        target,
                        claim,
                        "limits" if limitation_marker else "opposes",
                        evidence_id,
                        confidence,
                    )
            elif relation.relation == "rephrases":
                source_claim = ensure_claim(
                    relation.source_clause_id,
                    evidence_id,
                    confidence,
                )
                target_claim = ensure_claim(
                    relation.target_clause_id,
                    evidence_id,
                    confidence,
                )
                if source_claim and target_claim:
                    add_edge(
                        target_claim,
                        source_claim,
                        "rephrases",
                        evidence_id,
                        confidence,
                    )
            # `adds` is intentionally not promoted to a support edge. The design
            # contract treats it as supplementary evidence only.

        for attribution in attribution_frames:
            if attribution.status != ItemStatus.RESOLVED:
                continue
            add_component(
                "evidence",
                text=attribution.content_span.source_text,
                clause_id=attribution.clause_id,
                paragraph_id=paragraph_id_for(attribution.clause_id),
                source_span=attribution.content_span,
                evidence_ids=[f"ATTRIBUTION:{attribution.attribution_id}"],
                confidence=0.95,
            )

        argument_components = [
            *buckets["claim"],
            *buckets["reason"],
            *buckets["evidence"],
            *buckets["counterargument"],
            *buckets["rebuttal"],
            *buckets["limitation"],
        ]
        for operator in scope_operators:
            if (
                operator.operator_type != "condition"
                or operator.status != ItemStatus.RESOLVED
            ):
                continue
            targets = [
                item
                for item in argument_components
                if item.clause_id == operator.clause_id
                and item.component_type in {"claim", "reason"}
            ]
            if len(targets) != 1:
                unresolved.append({
                    "type": "argumentation_explicit_premise_target_ambiguous",
                    "operator_id": operator.operator_id,
                    "candidate_component_ids": [item.component_id for item in targets],
                    "status": "AMBIGUOUS",
                })
                continue
            target = targets[0]
            premise = add_component(
                "explicit_premise",
                text=operator.source_span.source_text,
                clause_id=operator.clause_id,
                paragraph_id=paragraph_id_for(operator.clause_id),
                source_span=operator.source_span,
                evidence_ids=[f"SCOPE:{operator.operator_id}"],
                related_component_ids=[target.component_id],
                confidence=0.98,
            )
            add_edge(
                premise,
                target,
                "conditions",
                f"SCOPE:{operator.operator_id}",
                0.98,
            )

        component_by_id = {
            item.component_id: item
            for values in buckets.values()
            for item in values
        }
        explicit_targets = {
            edge.target_component_id
            for edge in edges
            if edge.relation == "conditions"
        }
        for edge in list(edges):
            if (
                edge.relation != "supports"
                or support_relation_by_edge.get(edge.edge_id)
                not in {"justifies", "concludes"}
            ):
                continue
            source = component_by_id.get(edge.source_component_id)
            target = component_by_id.get(edge.target_component_id)
            if (
                source is None
                or target is None
                or source.component_type != "reason"
                or target.component_type != "claim"
                or target.component_id in explicit_targets
            ):
                continue
            candidate = add_component(
                "implicit_premise",
                text=None,
                evidence_ids=edge.evidence_ids,
                related_component_ids=[source.component_id, target.component_id],
                status="AMBIGUOUS",
                confidence=0.5,
            )
            unresolved.append({
                "type": "argumentation_implicit_premise",
                "reason": "warrant_not_explicit",
                "component_id": candidate.component_id,
                "related_component_ids": [source.component_id, target.component_id],
                "evidence_ids": edge.evidence_ids,
                "status": "AMBIGUOUS",
            })

        if not buckets["claim"]:
            unresolved.append({
                "type": "argumentation_claim_not_determined",
                "status": "AMBIGUOUS",
            })

        ambiguous_component = any(
            item.status == "AMBIGUOUS"
            for values in buckets.values()
            for item in values
        )
        result_status = (
            "AMBIGUOUS"
            if unresolved or ambiguous_component
            else "DETERMINED"
        )
        if not buckets["claim"]:
            confidence = 0.0
        else:
            base = (
                summary.confidence
                if summary is not None and summary.status == "DETERMINED"
                else 0.6
            )
            confidence = min(0.98, max(0.0, base) + min(0.2, 0.04 * len(edges)))
            if result_status == "AMBIGUOUS":
                confidence = min(confidence, 0.69)

        return ArgumentationResult(
            claims=buckets["claim"],
            reasons=buckets["reason"],
            evidence=buckets["evidence"],
            explicit_premises=buckets["explicit_premise"],
            implicit_premise_candidates=buckets["implicit_premise"],
            counterarguments=buckets["counterargument"],
            rebuttals=buckets["rebuttal"],
            limitations=buckets["limitation"],
            edges=edges,
            status=result_status,
            confidence=confidence,
            unresolved=unresolved,
        )

    @staticmethod
    def _ensure_entities(
        graph: MeaningGraph,
        frames: list[PredicateFrame],
    ) -> tuple[list[Entity], list[PredicateFrame]]:
        entities = list(graph.entities)
        by_key = {
            _compact(value): entity
            for entity in entities
            for value in [entity.canonical, *entity.mentions]
            if _compact(value)
        }
        updated_frames: list[PredicateFrame] = []
        for frame in frames:
            arguments: list[Argument] = []
            for argument in frame.arguments:
                key = _compact(argument.value)
                entity = by_key.get(key)
                if entity is None and key:
                    entity = Entity(
                        entity_id=f"E-{len(entities) + 1:03d}",
                        canonical=argument.value,
                        entity_type=(
                            "person_or_role"
                            if argument.role == "agent"
                            else "semantic_entity"
                        ),
                        mentions=[argument.value],
                        source_spans=[argument.span] if argument.span else [],
                        salience=45,
                    )
                    entities.append(entity)
                    by_key[key] = entity
                arguments.append(argument.model_copy(update={
                    "entity_id": entity.entity_id if entity else None,
                }))
            updated_frames.append(frame.model_copy(update={
                "arguments": arguments,
            }))
        return entities, updated_frames

    def enrich(
        self,
        graph: MeaningGraph,
        *,
        tokens: list[Token],
        original_text: str,
        update_hash: bool = True,
    ) -> MeaningGraph:
        frames: list[PredicateFrame] = []
        arcs: list[DependencyArc] = []
        unresolved: list[dict] = []
        frame_by_clause: dict[str, list[PredicateFrame]] = {}

        for clause in graph.clauses:
            indices = _clause_token_indices(clause, tokens)
            heads = _predicate_heads(indices, tokens)
            previous_end_position = -1
            for head_index in heads:
                if len(frames) >= self.max_frames:
                    unresolved.append({
                        "type": "reading_frame_limit",
                        "status": ItemStatus.TIMEOUT.value,
                    })
                    break
                head_position = indices.index(head_index)
                argument_indices = indices[previous_end_position + 1:head_position]
                arguments_with_heads = _arguments_before(
                    argument_indices,
                    tokens,
                    original_text,
                )
                start, end, predicate, surface = _predicate_bounds(
                    head_index,
                    indices,
                    tokens,
                )
                voice = _voice(clause.text)
                arguments = _arguments_for_voice(
                    [item[0] for item in arguments_with_heads],
                    voice,
                )
                frame = PredicateFrame(
                    frame_id=f"PF-{len(frames) + 1:03d}",
                    clause_id=clause.clause_id,
                    predicate=predicate,
                    surface_predicate=surface,
                    predicate_token_index=head_index,
                    arguments=arguments,
                    polarity=(
                        "negative"
                        if _has_semantic_negation(clause.text)
                        else "positive"
                    ),
                    tense=_tense(clause.text),
                    aspect=_aspect(clause.text),
                    voice=voice,
                    modality=_modalities(clause.text),
                    source_span=_span(start, end, original_text),
                )
                frames.append(frame)
                frame_by_clause.setdefault(clause.clause_id, []).append(frame)
                for argument, dependent_index in arguments_with_heads:
                    arcs.append(DependencyArc(
                        arc_id=f"DA-{len(arcs) + 1:03d}",
                        clause_id=clause.clause_id,
                        dependent_token_index=dependent_index,
                        head_token_index=head_index,
                        relation=argument.role,
                        marker=argument.case_marker,
                        confidence=0.98,
                    ))
                end_positions = [
                    position
                    for position, index in enumerate(indices)
                    if tokens[index].span.end <= end
                ]
                previous_end_position = max(end_positions, default=head_position)

        entities, frames = self._ensure_entities(graph, frames)
        frame_updates: dict[str, PredicateFrame] = {}
        for clause in graph.clauses:
            clause_frames = sorted(
                [frame for frame in frames if frame.clause_id == clause.clause_id],
                key=lambda item: item.source_span.start,
            )
            for index, frame in enumerate(clause_frames):
                next_frame = (
                    clause_frames[index + 1]
                    if index + 1 < len(clause_frames)
                    else None
                )
                local_end = (
                    next_frame.source_span.start
                    if next_frame is not None
                    else clause.source_span.end
                )
                local_end = max(local_end, frame.source_span.end)
                local_text = original_text[frame.source_span.start:local_end]
                frame_updates[frame.frame_id] = frame.model_copy(update={
                    "polarity": (
                        "negative"
                        if _has_semantic_negation(local_text)
                        else "positive"
                    ),
                    "tense": _tense(local_text),
                    "aspect": _aspect(local_text),
                    "voice": _voice(local_text),
                    "modality": _modalities(local_text),
                })
        frames = [
            (updated := frame_updates.get(frame.frame_id, frame)).model_copy(
                update={
                    "arguments": _arguments_for_voice(
                        updated.arguments,
                        updated.voice,
                    )
                }
            )
            for frame in frames
        ]

        frame_by_clause = {}
        for frame in frames:
            frame_by_clause.setdefault(frame.clause_id, []).append(frame)

        propositions = _ensure_gratitude_proposition(
            list(graph.propositions),
            graph.clauses,
            original_text,
        )
        propositions = _align_observation_propositions_with_frames(
            propositions,
            frame_by_clause,
        )
        clauses: list[Clause] = []
        frame_index_by_id = {
            item.frame_id: index for index, item in enumerate(frames)
        }
        for clause in graph.clauses:
            clause_frames = frame_by_clause.get(clause.clause_id, [])
            related = [
                item
                for item in propositions
                if item.clause_id == clause.clause_id
            ]
            main = (
                _primary_predicate_frame(clause_frames)
                if clause_frames
                else None
            )
            if (
                main is not None
                and _clause_needs_matrix_observation(
                    related,
                    clause_frames,
                    main,
                    clause_text=clause.text,
                )
            ):
                proposition = Proposition(
                    proposition_id=f"P-{len(propositions) + 1:03d}",
                    predicate=main.predicate,
                    surface_predicate=main.surface_predicate,
                    intent_type="observation",
                    value=clause.text,
                    arguments=main.arguments,
                    polarity=main.polarity,
                    sentence_mood=(
                        "interrogative"
                        if (
                            _CAPABILITY_QUESTION_RE.search(clause.text)
                            or re.search(r"[？?]", clause.text)
                        )
                        else "declarative"
                    ),
                    speech_act=(
                        "capability_question"
                        if _CAPABILITY_QUESTION_RE.search(clause.text)
                        else (
                            "question"
                            if re.search(r"[？?]", clause.text)
                            else "assertion"
                        )
                    ),
                    epistemic_status=(
                        "hearsay" if "hearsay" in main.modality else "asserted"
                    ),
                    tense=main.tense,
                    aspect=main.aspect,
                    voice=main.voice,
                    executable_candidate=False,
                    clause_id=clause.clause_id,
                    source_span=clause.source_span,
                    evidence_ids=["READING:PREDICATE_FRAME"],
                    inference_sources=["deterministic-reading-runtime"],
                )
                propositions.append(proposition)
                related = [
                    item
                    for item in propositions
                    if item.clause_id == clause.clause_id
                ]
            related_ids = [item.proposition_id for item in related]
            for frame in clause_frames:
                index = frame_index_by_id[frame.frame_id]
                frames[index] = frame.model_copy(update={
                    "related_proposition_ids": related_ids,
                })
            clauses.append(clause.model_copy(update={
                "proposition_ids": list(dict.fromkeys([
                    *clause.proposition_ids,
                    *related_ids,
                ])),
            }))

        operators: list[ScopeOperator] = []
        for clause in clauses:
            if len(operators) >= self.max_operators:
                unresolved.append({
                    "type": "reading_scope_limit",
                    "status": ItemStatus.TIMEOUT.value,
                })
                break
            values, missing = _operators_for_clause(
                clause,
                original_text,
                frame_by_clause.get(clause.clause_id, []),
                len(operators) + 1,
            )
            remaining = self.max_operators - len(operators)
            operators.extend(values[:remaining])
            unresolved.extend(missing)

        for start, end, source in quote_ranges(original_text):
            if len(operators) >= self.max_operators:
                break
            clause = next(
                (
                    item
                    for item in clauses
                    if item.source_span.start <= start < item.source_span.end
                ),
                None,
            )
            if clause is None:
                continue
            operators.append(ScopeOperator(
                operator_id=f"SO-{len(operators) + 1:03d}",
                clause_id=clause.clause_id,
                operator_type="quotation",
                semantic_value="quoted_content",
                marker=source,
                source_span=_span(start, end, original_text),
                operand_spans=[_span(start, end, original_text)],
                target_frame_ids=[
                    item.frame_id
                    for item in frames
                    if start <= item.source_span.start and item.source_span.end <= end
                ],
            ))

        discourse = _discourse_relations(clauses)
        attributions = _attributions(original_text, clauses, frames)
        unresolved.extend([
            {
                "type": "reading_attribution_source",
                "attribution_id": item.attribution_id,
                "status": item.status.value,
                "source_span": item.content_span.model_dump(),
            }
            for item in attributions
            if item.status != ItemStatus.RESOLVED
        ])
        status = (
            ItemStatus.RESOLVED
            if not unresolved
            else (
                ItemStatus.TIMEOUT
                if any(item.get("status") == ItemStatus.TIMEOUT.value for item in unresolved)
                else ItemStatus.INSUFFICIENT
            )
        )
        paragraph_structure = self._detect_paragraphs(
            original_text,
            clauses,
        )
        summary = self._extract_summary(paragraph_structure)
        argumentation = self._extract_argumentation(
            paragraph_structure=paragraph_structure,
            summary=summary,
            clauses=clauses,
            discourse_relations=discourse,
            scope_operators=operators,
            attribution_frames=attributions,
        )
        reading = ReadingAnalysis(
            predicate_frames=frames,
            dependency_arcs=arcs,
            scope_operators=operators,
            attribution_frames=attributions,
            discourse_relations=discourse,
            paragraph_structure=paragraph_structure,
            summary=summary,
            argumentation=argumentation,
            unresolved=unresolved,
            status=status,
        )
        propositions = _drop_conditional_connection_propositions(
            propositions,
            operators,
        )
        propositions = _rewrite_generic_request_propositions(
            propositions,
            frame_by_clause,
        )
        propositions = _ensure_completion_criteria_propositions(
            propositions,
            clauses,
            original_text,
            operators,
        )
        propositions = _rewrite_gratitude_with_incomplete_tail(
            propositions,
            original_text,
            frame_by_clause,
        )
        propositions = _drop_spurious_preserve_propositions(
            propositions,
            frame_by_clause,
            original_text=original_text,
            operators=operators,
        )
        propositions = _ensure_observations_for_predicate_frames(
            propositions,
            clauses,
            frame_by_clause,
            operators,
        )
        propositions = _dedupe_propositions(propositions)
        propositions = _normalize_concessive_and_contrast_propositions(
            propositions,
            original_text=original_text,
            operators=operators,
            discourse=discourse,
        )
        propositions = _prune_redundant_observations(propositions)
        if _COMPLETION_WITH_HOLDING_RE.search(original_text) and any(
            item.intent_type == "completion_criteria"
            for item in propositions
        ):
            propositions = [
                item
                for item in propositions
                if item.intent_type != "observation"
                or item.predicate not in {"持つ", "為る", "する"}
            ]
        graph_unresolved = [
            *graph.unresolved,
            *[
                {**item, "reading_analysis": True}
                for item in unresolved
            ],
        ]
        propositions = [
            item.model_copy(update={
                "pragmatic_markers": list(dict.fromkeys([
                    *item.pragmatic_markers,
                    "pragmatic.capability_question",
                ])),
                "inference_sources": list(dict.fromkeys([
                    *item.inference_sources,
                    "pragmatic_profile:pragmatic.capability_question",
                ])),
            })
            if item.speech_act == "capability_question"
            else item
            for item in propositions
        ]
        quality = {
            **graph.quality_annotations,
            "reading_purpose": "japanese_reading_comprehension",
            "reading_predicate_frames": len(frames),
            "reading_dependency_arcs": len(arcs),
            "reading_scope_operators": len(operators),
            "reading_attribution_frames": len(attributions),
            "reading_discourse_relations": len(discourse),
            "reading_argumentation_claims": len(argumentation.claims),
            "reading_argumentation_edges": len(argumentation.edges),
            "reading_argumentation_status": argumentation.status,
            "reading_unresolved": len(unresolved),
            "reading_action_inference": False,
        }
        updated = graph.model_copy(update={
            "entities": entities,
            "clauses": clauses,
            "propositions": propositions,
            "reading_analysis": reading,
            "unresolved": graph_unresolved,
            "quality_annotations": quality,
        })
        if update_hash:
            updated = updated.model_copy(update={
                "semantic_hash": _stable_hash(updated),
            })
        self.last_metrics = {
            "reading_predicate_frame_count": len(frames),
            "reading_dependency_arc_count": len(arcs),
            "reading_scope_operator_count": len(operators),
            "reading_attribution_frame_count": len(attributions),
            "reading_discourse_relation_count": len(discourse),
            "reading_argumentation_claim_count": len(argumentation.claims),
            "reading_argumentation_edge_count": len(argumentation.edges),
            "reading_unresolved_count": len(unresolved),
        }
        return updated
