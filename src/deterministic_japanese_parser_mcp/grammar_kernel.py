from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re

from .models import Intent, OriginalSpan, Token


ACTION_INTENTS = {
    "request",
    "modify",
    "remove",
    "comparison",
    "action",
    "decision",
    "correction",
}
CONSTRAINT_INTENTS = {
    "prohibition",
    "preserve",
    "condition",
    "exception",
    "priority",
    "scope",
    "out_of_scope",
    "dependency",
    "completion_criteria",
    "verification_criteria",
    "premise",
    "sequence",
}

_PREDICATES = {
    "request": "要求する",
    "modify": "変更する",
    "remove": "削除する",
    "comparison": "比較する",
    "action": "実行する",
    "decision": "決定する",
    "correction": "訂正する",
    "prohibition": "禁止する",
    "preserve": "維持する",
    "condition": "条件とする",
    "exception": "例外とする",
    "priority": "優先する",
    "scope": "範囲を限定する",
    "out_of_scope": "範囲外とする",
    "dependency": "依存する",
    "completion_criteria": "完了条件とする",
    "verification_criteria": "検証条件とする",
    "premise": "前提とする",
    "sequence": "順序付ける",
    "question": "質問する",
    "reference": "参照する",
}

_ROLE_BY_CAPTURE = {
    "target": "object",
    "action": "action",
    "task": "task",
    "new": "result",
    "old": "previous",
    "condition": "condition",
    "exception": "exception",
    "dependency": "dependency",
    "first": "source",
    "second": "destination",
    "last": "destination",
    "scope": "scope",
    "premise": "premise",
    "criterion": "criterion",
    "reference": "reference",
}

_CASE_MARKERS = (
    ("から", "source"),
    ("まで", "limit"),
    ("より", "comparison_source"),
    ("へ", "destination"),
    ("に", "recipient"),
    ("を", "object"),
    ("が", "agent"),
    ("は", "topic"),
    ("で", "location_or_means"),
    ("と", "companion_or_quote"),
)

_QUOTE_PAIRS = {"「": "」", "『": "』", "“": "”", "‘": "’"}
_SENTENCE_END = re.compile(r"[。！？!?\n]+")
_INTRA_CLAUSE_BOUNDARY = re.compile(
    r"(?:ので|のに|けれども|けれど|けど|が、)"
)
_QUESTION_END = re.compile(r"(?:[？?]|(?:の|ん|だ|です|ます)?か[。！？!?]?$)")
_IMPERATIVE_END = re.compile(
    r"(?:しろ|せよ|やれ|直せ|変えろ|削除しろ|消せ|残せ|維持しろ|"
    r"比較しろ|決めろ|確認しろ|実行しろ|公開しろ|入れろ|塞げ|"
    r"するな|触るな|変更するな|削除するな|してください|してくれ)[。！？!?]?$"
)
_NEGATION = re.compile(r"(?:ない|なく|なかった|ぬ|ず|するな|禁止|不可|ではない)")
_EPISTEMIC = (
    (re.compile(r"(?:かもしれない|可能性がある)"), "possible"),
    (re.compile(r"(?:はずだ|はずです)"), "expected"),
    (re.compile(r"(?:らしい|そうだ|とのこと)"), "hearsay"),
    (re.compile(r"(?:と思う|と考える)"), "opinion"),
    (re.compile(r"(?:仮に|もし)"), "hypothetical"),
)

_PLAIN_FORM_RULE_IDS = {
    "ACTION-001",
    "ACTION-002",
    "REQUEST-009",
}
_PLAIN_FORM_TARGET_MARKERS = {"を", "と"}
_PLAIN_FORM_ARGUMENT_MARKERS = {"を", "と", "に", "へ", "で", "から", "まで"}
_PLAIN_FORM_NON_DIRECTIVE_PREDICATES = {
    "有る",
    "ある",
    "無い",
    "ない",
    "居る",
    "いる",
    "成る",
    "なる",
    "思う",
    "考える",
    "感じる",
    "見える",
    "分かる",
    "判る",
    "知れる",
}
_SELF_POLICY_TOPICS = {"私", "わたし", "我々", "当方", "自身"}


@dataclass(frozen=True)
class ClauseSeed:
    clause_id: str
    start: int
    end: int
    text: str

    @property
    def span(self) -> OriginalSpan:
        return OriginalSpan(start=self.start, end=self.end, source_text=self.text)


@dataclass(frozen=True)
class PlainFormDirective:
    clause: ClauseSeed
    target: str
    source_text: str
    predicate_start: int
    negative: bool
    explicit_matrix_agent: bool
    self_policy_topic: bool


def _token_is_predicate(token: Token) -> bool:
    return bool(token.pos and token.pos[0] in {"動詞", "形容詞", "形状詞"})


def _tokens_for_clause(clause: ClauseSeed, tokens: list[Token]) -> list[Token]:
    return [
        token
        for token in tokens
        if token.span.start < clause.end and clause.start < token.span.end
        and not (token.pos and token.pos[0] in {"補助記号", "空白"})
    ]


def _plain_form_directive(
    clause: ClauseSeed,
    tokens: list[Token],
    original_text: str,
) -> PlainFormDirective | None:
    values = _tokens_for_clause(clause, tokens)
    if not values:
        return None

    final = values[-1]
    previous = values[-2] if len(values) > 1 else None
    verbal_negative_tail = bool(
        final.surface in {"ない", "ぬ", "ません"}
        and previous is not None
        and (
            _token_is_predicate(previous)
            or (previous.pos and previous.pos[0] == "助動詞")
        )
    )
    negative = bool(
        final.normalized in {"ぬ"}
        or final.surface in {"ぬ", "ません"}
        or verbal_negative_tail
    )
    head_position = len(values) - 1
    if negative:
        head_position -= 1
        while head_position >= 0 and not _token_is_predicate(values[head_position]):
            head_position -= 1
        if head_position < 0:
            return None
    elif not _token_is_predicate(final):
        return None

    head = values[head_position]
    inflection = head.pos[5] if len(head.pos) > 5 else ""
    if not negative and not inflection.startswith(("終止形", "連体形")):
        return None
    if head.normalized in _PLAIN_FORM_NON_DIRECTIVE_PREDICATES:
        return None

    predicate_start_position = head_position
    if (
        head.normalized in {"為る", "する"}
        and head_position > 0
        and values[head_position - 1].pos[:3] == ["名詞", "普通名詞", "サ変可能"]
    ):
        predicate_start_position -= 1

    prefix = values[:predicate_start_position]
    if not prefix:
        return None
    argument_markers = [
        (position, token)
        for position, token in enumerate(prefix)
        if token.surface in _PLAIN_FORM_ARGUMENT_MARKERS
    ]
    if not argument_markers:
        return None

    target_markers = [
        (position, token)
        for position, token in argument_markers
        if token.surface in _PLAIN_FORM_TARGET_MARKERS
    ]
    target_marker = target_markers[-1][1] if target_markers else None
    target_end = (
        target_marker.span.start
        if target_marker is not None
        else values[predicate_start_position].span.start
    )
    target = clean_fragment(original_text[clause.start:target_end])
    if not target:
        return None

    matrix_agent_tokens: list[Token] = []
    boundary_position = (
        target_markers[-1][0]
        if target_markers
        else predicate_start_position
    )
    for position, token in enumerate(prefix[:boundary_position]):
        if token.surface not in {"は", "が"}:
            continue
        predicate_before = any(_token_is_predicate(item) for item in prefix[:position])
        predicate_after = any(
            _token_is_predicate(item)
            for item in prefix[position + 1:boundary_position]
        )
        if not predicate_before and not predicate_after:
            matrix_agent_tokens = prefix[:position]
            break

    explicit_matrix_agent = bool(matrix_agent_tokens)
    topic = "".join(item.surface for item in matrix_agent_tokens)
    self_policy_topic = bool(
        topic
        and (
            any(value in topic for value in _SELF_POLICY_TOPICS)
            or topic.endswith("自身")
        )
    )
    return PlainFormDirective(
        clause=clause,
        target=target,
        source_text=original_text[clause.start:clause.end].rstrip(
            "\u3002\uff01\uff1f!?\n"
        ),
        predicate_start=values[predicate_start_position].span.start,
        negative=negative,
        explicit_matrix_agent=explicit_matrix_agent,
        self_policy_topic=self_policy_topic,
    )


def discover_plain_form_directives(
    original_text: str,
    tokens: list[Token],
    intents: list[Intent],
) -> list[Intent]:
    """Complete sentence-local plain-form directives using grammar evidence.

    Positive plain forms are not auto-promoted to requests; an explicit intent rule
    must provide that authority. Negative plain forms become prohibitions only with
    an omitted agent or a self-policy topic. Third-person factual declaratives remain observations.
    """
    clauses = segment_clauses(original_text)
    profiles = {
        clause.clause_id: (None if _QUESTION_END.search(clause.text.strip()) else _plain_form_directive(clause, tokens, original_text))
        for clause in clauses
    }

    def profile_for(intent: Intent) -> PlainFormDirective | None:
        clause = clause_for_span(intent.span, clauses)
        return profiles.get(clause.clause_id) if clause else None

    output: list[Intent] = []
    for intent in intents:
        if intent.rule_id in _PLAIN_FORM_RULE_IDS:
            profile = profile_for(intent)
            if (
                profile is not None
                and profile.explicit_matrix_agent
                and not profile.self_policy_topic
            ):
                continue
        output.append(intent)

    for clause in clauses:
        profile = profiles.get(clause.clause_id)
        if profile is None:
            continue
        existing = [
            item
            for item in output
            if item.type in ACTION_INTENTS | {"prohibition"}
            and clause.start < item.span.end
            and item.span.start < clause.end
        ]
        if profile.negative:
            if profile.explicit_matrix_agent and not profile.self_policy_topic:
                continue
            if any(item.type == "prohibition" for item in existing):
                continue
            intent_type = "prohibition"
            rule_id = "GRAMMAR-PLAIN-PROHIBITION-001"
            value = profile.source_text
            captures = {"action": profile.source_text}
        else:
            continue
        source_end = clause.end
        while source_end > clause.start and original_text[source_end - 1] in "。！？!?\n":
            source_end -= 1
        output.append(Intent(
            type=intent_type,
            value=value,
            captures=captures,
            rule_id=rule_id,
            priority=50,
            span=OriginalSpan(
                start=clause.start,
                end=source_end,
                source_text=original_text[clause.start:source_end],
            ),
        ))
    return output


def quote_ranges(text: str) -> list[tuple[int, int, str]]:
    stack: list[tuple[str, int]] = []
    ranges: list[tuple[int, int, str]] = []
    for index, char in enumerate(text):
        if char in _QUOTE_PAIRS:
            stack.append((char, index))
            continue
        if not stack:
            continue
        opener, start = stack[-1]
        if char == _QUOTE_PAIRS[opener]:
            stack.pop()
            ranges.append((start, index + 1, text[start:index + 1]))
    return sorted(ranges)


def is_inside_quote(
    span: OriginalSpan,
    ranges: list[tuple[int, int, str]],
) -> tuple[bool, str | None]:
    for start, end, source in ranges:
        if start <= span.start and span.end <= end:
            return True, source
    return False, None


def _append_clause_span(
    seeds: list[ClauseSeed],
    text: str,
    start: int,
    end: int,
) -> None:
    raw_start = start
    raw_end = end
    while raw_start < raw_end and text[raw_start].isspace():
        raw_start += 1
    while raw_end > raw_start and text[raw_end - 1].isspace():
        raw_end -= 1
    if raw_start >= raw_end:
        return
    seeds.append(ClauseSeed(
        clause_id=f"C-{len(seeds) + 1:03d}",
        start=raw_start,
        end=raw_end,
        text=text[raw_start:raw_end],
    ))


def _append_clause_with_discourse_boundaries(
    seeds: list[ClauseSeed],
    text: str,
    start: int,
    end: int,
) -> None:
    cursor = start
    for match in _INTRA_CLAUSE_BOUNDARY.finditer(text, start, end):
        split = match.end()
        if split >= end:
            continue
        tail = text[split:end].strip(" \t\r\n、。！？!?")
        if not tail:
            continue
        _append_clause_span(seeds, text, cursor, split)
        cursor = split
    _append_clause_span(seeds, text, cursor, end)


def segment_clauses(text: str) -> list[ClauseSeed]:
    seeds: list[ClauseSeed] = []
    cursor = 0
    for match in _SENTENCE_END.finditer(text):
        end = match.end()
        _append_clause_with_discourse_boundaries(seeds, text, cursor, end)
        cursor = end
    if cursor < len(text):
        _append_clause_with_discourse_boundaries(
            seeds, text, cursor, len(text)
        )
    if not seeds and text:
        seeds.append(ClauseSeed(
            clause_id="C-001",
            start=0,
            end=len(text),
            text=text,
        ))
    return seeds


def clause_for_span(
    span: OriginalSpan,
    clauses: list[ClauseSeed],
) -> ClauseSeed | None:
    best: ClauseSeed | None = None
    overlap = -1
    for clause in clauses:
        current = max(
            0,
            min(span.end, clause.end) - max(span.start, clause.start),
        )
        if current > overlap:
            best = clause
            overlap = current
    return best


def predicate_for(intent_type: str) -> str:
    return _PREDICATES.get(intent_type, intent_type)


def target_for(intent: Intent) -> str:
    for key in ("target", "action", "task", "new", "scope", "reference"):
        value = intent.captures.get(key)
        if value:
            return clean_fragment(value)
    return clean_fragment(intent.value)


def clean_fragment(value: str) -> str:
    cleaned = value.strip(" \t\r\n、。！？!?「」『』\"'")
    cleaned = re.sub(r"^(?:そして|また|ただし|なお|次に|最後に)", "", cleaned)
    cleaned = re.sub(r"(?:だけ|のみ)$", "", cleaned)
    return cleaned.strip()


def case_role(value: str) -> tuple[str | None, str | None]:
    for marker, role in _CASE_MARKERS:
        if value.endswith(marker) and len(value) > len(marker):
            return marker, role
    return None, None


def infer_sentence_mood(text: str, intent_type: str) -> str:
    stripped = text.strip()
    if intent_type == "question" or _QUESTION_END.search(stripped):
        return "interrogative"
    if (
        intent_type in ACTION_INTENTS | {"prohibition", "preserve"}
        or _IMPERATIVE_END.search(stripped)
    ):
        return "imperative"
    return "declarative"


def infer_speech_act(intent_type: str, mood: str) -> str:
    if mood == "interrogative":
        return "question"
    if intent_type == "prohibition":
        return "command"
    if intent_type in {
        "request",
        "modify",
        "remove",
        "action",
        "comparison",
        "correction",
    }:
        return "command" if mood == "imperative" else "request"
    if intent_type == "decision":
        return "decision"
    if intent_type == "question":
        return "question"
    return "assertion"


def infer_deontic_force(intent_type: str, text: str) -> str:
    if intent_type == "prohibition" or re.search(
        r"(?:するな|してはいけない|禁止)", text
    ):
        return "prohibition"
    if intent_type in ACTION_INTENTS or re.search(r"(?:べき|必要|必須)", text):
        return "obligation"
    if re.search(r"(?:してよい|許可|可能)", text):
        return "permission"
    return "none"


def infer_polarity(intent_type: str, text: str) -> str:
    if intent_type == "prohibition" or _NEGATION.search(text):
        return "negative"
    return "positive"


def infer_epistemic_status(text: str) -> str:
    for pattern, value in _EPISTEMIC:
        if pattern.search(text):
            return value
    return "asserted"


def argument_roles(intent: Intent) -> list[tuple[str, str, str | None]]:
    output: list[tuple[str, str, str | None]] = []
    seen: set[tuple[str, str]] = set()
    for key, raw in intent.captures.items():
        value = clean_fragment(raw)
        if not value:
            continue
        role = _ROLE_BY_CAPTURE.get(key, key)
        marker, inferred = case_role(value)
        if inferred and role in {"object", "action", "task"}:
            role = inferred
        item = (role, value, marker)
        if (role, value) not in seen:
            output.append(item)
            seen.add((role, value))
    if not output:
        value = target_for(intent)
        if value:
            marker, role = case_role(value)
            output.append((role or "object", value, marker))
    return output


def context_version(context: list[str], known_entities: list[str]) -> str:
    payload = json.dumps(
        {"context": context, "known_entities": known_entities},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
