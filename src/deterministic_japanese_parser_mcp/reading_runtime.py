from __future__ import annotations

import hashlib
import re

from .grammar_kernel import quote_ranges
from .models import (
    Argument,
    AttributionFrame,
    Clause,
    DependencyArc,
    DiscourseRelation,
    Entity,
    ItemStatus,
    MeaningGraph,
    OriginalSpan,
    PredicateFrame,
    Proposition,
    ReadingAnalysis,
    ScopeOperator,
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
            heads.append(index)
            continue
        if _pos0(token) == "名詞" and position + 1 < len(indices):
            following = tokens[indices[position + 1]]
            if following.surface in _COPULAS:
                heads.append(index)
    return heads


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
    for index in indices:
        token = tokens[index]
        if _is_punctuation(token):
            buffer = []
            continue
        role = _CASE_ROLES.get(token.surface)
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
                case_marker=token.surface,
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
    if re.search(r"(?:られる|れる)", text):
        return ["passive_or_potential"]
    if re.search(r"(?:できる|可能だ|可能です)", text):
        return ["potential"]
    return ["active"]


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
        targets = [item.frame_id for item in frames]
        operands = [clause.source_span]
        if operator_type == "condition":
            operands = [
                _span(clause.source_span.start, end, original),
                _span(end, clause.source_span.end, original),
            ]
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
            add("modality", value, match)
    for pattern, value in _QUANTIFIER_PATTERNS:
        for match in pattern.finditer(clause.text):
            add("quantifier", value, match)
    if re.search(r"[？?]|(?:の|ん|だ|です|ます)?か[。！？!?]?$", clause.text):
        match = re.search(r"[？?]|か(?=[。！？!?]?$)", clause.text)
        if match:
            add("question", "interrogative", match)
    return output, unresolved


def _discourse_relations(clauses: list[Clause]) -> list[DiscourseRelation]:
    output: list[DiscourseRelation] = []
    ordered = sorted(clauses, key=lambda item: item.source_span.start)
    for previous, current in zip(ordered, ordered[1:]):
        stripped = current.text.lstrip()
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
                frame = PredicateFrame(
                    frame_id=f"PF-{len(frames) + 1:03d}",
                    clause_id=clause.clause_id,
                    predicate=predicate,
                    surface_predicate=surface,
                    predicate_token_index=head_index,
                    arguments=[item[0] for item in arguments_with_heads],
                    polarity=(
                        "negative"
                        if _has_semantic_negation(clause.text)
                        else "positive"
                    ),
                    tense=_tense(clause.text),
                    aspect=_aspect(clause.text),
                    voice=_voice(clause.text),
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
        frame_by_clause = {}
        for frame in frames:
            frame_by_clause.setdefault(frame.clause_id, []).append(frame)

        propositions = list(graph.propositions)
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
            if not related and clause_frames:
                main = clause_frames[-1]
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
                        if re.search(r"[？?]", clause.text)
                        else "declarative"
                    ),
                    speech_act=(
                        "question"
                        if re.search(r"[？?]", clause.text)
                        else "assertion"
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
                related = [proposition]
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
        reading = ReadingAnalysis(
            predicate_frames=frames,
            dependency_arcs=arcs,
            scope_operators=operators,
            attribution_frames=attributions,
            discourse_relations=discourse,
            unresolved=unresolved,
            status=status,
        )
        graph_unresolved = [
            *graph.unresolved,
            *[
                {**item, "reading_analysis": True}
                for item in unresolved
            ],
        ]
        quality = {
            **graph.quality_annotations,
            "reading_purpose": "japanese_reading_comprehension",
            "reading_predicate_frames": len(frames),
            "reading_dependency_arcs": len(arcs),
            "reading_scope_operators": len(operators),
            "reading_attribution_frames": len(attributions),
            "reading_discourse_relations": len(discourse),
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
            "reading_unresolved_count": len(unresolved),
        }
        return updated
