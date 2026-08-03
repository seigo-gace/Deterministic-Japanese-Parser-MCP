from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re

from .models import Intent, OriginalSpan


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


@dataclass(frozen=True)
class ClauseSeed:
    clause_id: str
    start: int
    end: int
    text: str

    @property
    def span(self) -> OriginalSpan:
        return OriginalSpan(start=self.start, end=self.end, source_text=self.text)


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


def segment_clauses(text: str) -> list[ClauseSeed]:
    seeds: list[ClauseSeed] = []
    cursor = 0
    index = 1
    for match in _SENTENCE_END.finditer(text):
        end = match.end()
        raw_start = cursor
        raw_end = end
        while raw_start < raw_end and text[raw_start].isspace():
            raw_start += 1
        while raw_end > raw_start and text[raw_end - 1].isspace():
            raw_end -= 1
        if raw_start < raw_end:
            seeds.append(ClauseSeed(
                clause_id=f"C-{index:03d}",
                start=raw_start,
                end=raw_end,
                text=text[raw_start:raw_end],
            ))
            index += 1
        cursor = end
    if cursor < len(text):
        raw_start = cursor
        raw_end = len(text)
        while raw_start < raw_end and text[raw_start].isspace():
            raw_start += 1
        while raw_end > raw_start and text[raw_end - 1].isspace():
            raw_end -= 1
        if raw_start < raw_end:
            seeds.append(ClauseSeed(
                clause_id=f"C-{index:03d}",
                start=raw_start,
                end=raw_end,
                text=text[raw_start:raw_end],
            ))
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
