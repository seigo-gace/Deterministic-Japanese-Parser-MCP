from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

import yaml

from .canonical import Canonicalizer
from .grammar_kernel import (
    ACTION_INTENTS,
    clean_fragment,
    infer_epistemic_status,
    infer_polarity,
    is_inside_quote,
    quote_ranges,
)
from .models import (
    Argument,
    Clause,
    Entity,
    ItemStatus,
    MeaningGraph,
    Metaphor,
    OriginalSpan,
    Proposition,
    ScopeEdge,
    SenseCandidate,
    Token,
)

_TARGET_ROLES = {
    "object",
    "task",
    "action",
    "result",
    "scope",
    "reference",
    "destination",
}
_EXECUTABLE_SPEECH_ACTS = {"command", "request", "polite_request"}
_GENERIC_TARGETS = {
    "これ",
    "それ",
    "もの",
    "こと",
    "内容",
    "対応",
    "作業",
    "処理",
    "実行",
    "確認",
    "修正",
    "変更",
    "削除",
    "公開",
    "保存",
    "共有",
    "テスト",
}
_CASE_ROLE = {
    "を": "object",
    "は": "topic",
    "が": "agent",
    "に": "recipient",
    "へ": "destination",
    "で": "location_or_means",
    "から": "source",
    "と": "companion_or_quote",
}
_ACTION_PREDICATE = {
    "確認": ("action", "確認する"),
    "共有": ("action", "共有する"),
    "修正": ("modify", "変更する"),
    "変更": ("modify", "変更する"),
    "更新": ("modify", "変更する"),
    "書き換え": ("modify", "変更する"),
    "削除": ("remove", "削除する"),
    "消去": ("remove", "削除する"),
    "外す": ("remove", "削除する"),
    "公開": ("action", "公開する"),
    "保存": ("action", "保存する"),
    "送信": ("action", "送信する"),
    "実行": ("action", "実行する"),
    "検証": ("action", "検証する"),
    "テスト": ("action", "検証する"),
    "再起動": ("action", "再起動する"),
}
_PRAGMATIC_DOMAIN_MAP = {
    "間接拒否": ("refusal", "refusal", False),
    "婉曲否定": ("refusal", "refusal", False),
    "保留回答": ("deferral", "deferral", False),
    "懸念表明": ("concern", "concern", False),
    "進行懸念": ("concern", "concern", False),
    "確認要求": (
        "clarification_request",
        "clarification_request",
        False,
    ),
    "情報要求": (
        "clarification_request",
        "clarification_request",
        False,
    ),
    "判断不能": ("inability", "inability", False),
    "前置き": ("mitigation", "mitigation", False),
    "再検討": ("proposal", "proposal", False),
    "代替要求": ("request", "request", True),
    "整理提案": ("request", "request", True),
    "認識合わせ": ("clarification_request", "request", False),
}
_EXTRA_PRAGMATIC_PATTERNS = {
    "pragmatic.refusal": [
        r"今.{0,24}(?:難しい|できない|対応できません)",
        r"今回は.{0,16}(?:見送|控え)",
    ],
    "pragmatic.polite_request": [
        r"(?:確認|共有|修正|変更|更新|削除|公開|保存|送信|実行|検証|テスト)"
        r"して(?:いただけますか|もらえませんか|いただけないでしょうか)",
    ],
}
_EXTRA_BARE_ACTIONS = [
    {
        "intent_type": "remove",
        "predicate": "削除する",
        "patterns": [
            r"(?:削除|消去)(?:して|しろ|してください|してくれ|してほしい)"
            r"(?:。|、|$)",
            r"(?:消し|外し)(?:て|ろ|てください|てくれ|てほしい)(?:。|、|$)",
        ],
    },
]
_ACTION_EXTRACT = re.compile(
    r"(?P<target>[^、。！？!?]{1,48}?)(?:を|は)?"
    r"(?P<action>確認|共有|修正|変更|更新|書き換え|削除|消去|外す|"
    r"公開|保存|送信|実行|検証|テスト|再起動)"
    r"(?:していただけますか|してもらえませんか|していただけないでしょうか|"
    r"してください|してほしい|してくれ|して|しろ|せよ|てください|てくれ|てほしい)"
)


def _compact(value: str) -> str:
    return re.sub(r"[\s、。！？!?「」『』\"'()（）]+", "", value or "")


def _overlap(left: OriginalSpan, right: OriginalSpan) -> bool:
    return left.start < right.end and right.start < left.end


def _span(start: int, end: int, original: str) -> OriginalSpan:
    return OriginalSpan(start=start, end=end, source_text=original[start:end])


def _clause_for_position(
    clauses: list[Clause],
    start: int,
    end: int,
) -> Clause | None:
    containing = [
        item
        for item in clauses
        if item.source_span.start <= start < item.source_span.end
    ]
    if containing:
        return min(
            containing,
            key=lambda item: item.source_span.end - item.source_span.start,
        )
    return None


def _stable_hash(graph: MeaningGraph) -> str:
    payload = graph.model_dump(exclude={"semantic_hash"}, mode="json")
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class _Antecedent:
    value: str
    entity_id: str | None
    score: int
    reason: str


class SemanticEnricher:
    """Evidence-backed deterministic semantic enrichment.

    This layer never invents a sense or referent when the configured evidence
    is insufficient. Ambiguous executable propositions are made non-executable.
    """

    def __init__(self, profile_path: Path, canonicalizer: Canonicalizer):
        self.profile_path = profile_path
        self.canonicalizer = canonicalizer
        self.doc = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
        self.senses = self.doc.get("senses", {})
        self.compiled_senses: dict[str, list[dict]] = {}
        for lemma, profile in self.senses.items():
            values: list[dict] = []
            for item in profile.get("senses", []):
                value = dict(item)
                value["compiled_patterns"] = [
                    re.compile(pattern)
                    for pattern in item.get("patterns", [])
                ]
                values.append(value)
            self.compiled_senses[lemma] = values

        self.pragmatics: list[dict] = []
        for item in self.doc.get("pragmatics", []):
            value = dict(item)
            patterns = [
                *item.get("patterns", []),
                *_EXTRA_PRAGMATIC_PATTERNS.get(item["id"], []),
            ]
            value["compiled_patterns"] = [
                re.compile(pattern) for pattern in patterns
            ]
            self.pragmatics.append(value)

        self.bare_actions: list[dict] = []
        for item in [
            *self.doc.get("bare_actions", []),
            *_EXTRA_BARE_ACTIONS,
        ]:
            value = dict(item)
            value["compiled_patterns"] = [
                re.compile(pattern)
                for pattern in item.get("patterns", [])
            ]
            self.bare_actions.append(value)
        self.last_metrics: dict[str, int | float] = {}

    @staticmethod
    def _entity_index(entities: list[Entity]) -> dict[str, Entity]:
        output: dict[str, Entity] = {}
        for entity in entities:
            for value in [entity.canonical, *entity.mentions, *entity.aliases]:
                key = _compact(value)
                if key:
                    output.setdefault(key, entity)
        return output

    @staticmethod
    def _ensure_entity(
        entities: list[Entity],
        index: dict[str, Entity],
        value: str,
        *,
        span: OriginalSpan | None = None,
        entity_type: str = "semantic_entity",
        salience: int = 25,
    ) -> str | None:
        value = clean_fragment(value)
        key = _compact(value)
        if not key:
            return None
        existing = index.get(key)
        if existing is not None:
            return existing.entity_id
        entity = Entity(
            entity_id=f"E-{len(entities) + 1:03d}",
            canonical=value,
            entity_type=entity_type,
            mentions=[value],
            source_spans=[span] if span else [],
            salience=salience,
            status=ItemStatus.RESOLVED,
        )
        entities.append(entity)
        index[key] = entity
        return entity.entity_id

    @staticmethod
    def _nearest_argument(
        original_text: str,
        clause: Clause,
        predicate_start: int,
    ) -> tuple[str, str, OriginalSpan] | None:
        prefix = original_text[clause.source_span.start:predicate_start]
        segment = re.split(r"[、。！？!?]", prefix)[-1].strip()
        match = re.search(
            r"(?P<value>[^、。！？!?]{1,48}?)(?P<marker>から|まで|より|を|は|が|に|へ|で|と)$",
            segment,
        )
        if not match:
            return None
        value = clean_fragment(match.group("value"))
        if not value:
            return None
        relative = prefix.rfind(match.group("value"))
        start = clause.source_span.start + relative
        return (
            value,
            match.group("marker"),
            _span(start, start + len(match.group("value")), original_text),
        )

    @staticmethod
    def _target_arguments(proposition: Proposition) -> list[Argument]:
        return [
            item
            for item in proposition.arguments
            if item.role in _TARGET_ROLES and item.value
        ]

    @staticmethod
    def _action_details(text: str) -> tuple[str | None, str | None, str | None]:
        match = _ACTION_EXTRACT.search(text)
        if not match:
            return None, None, None
        target = clean_fragment(match.group("target")) or None
        action = match.group("action")
        intent_type, predicate = _ACTION_PREDICATE[action]
        return target, intent_type, predicate

    def _argument_for_target(
        self,
        target: str,
        span: OriginalSpan,
        original_text: str,
        entities: list[Entity],
        entity_index: dict[str, Entity],
        *,
        explicit: bool,
    ) -> Argument:
        start = original_text.find(target, span.start, span.end)
        target_span = (
            _span(start, start + len(target), original_text)
            if start >= 0
            else None
        )
        entity_id = self._ensure_entity(
            entities,
            entity_index,
            target,
            span=target_span,
            salience=45,
        )
        return Argument(
            role="object",
            value=target,
            entity_id=entity_id,
            case_marker="を" if explicit else None,
            explicit=explicit,
            span=target_span,
        )

    def _create_bare_actions(
        self,
        original_text: str,
        clauses: list[Clause],
        propositions: list[Proposition],
        entities: list[Entity],
        entity_index: dict[str, Entity],
    ) -> tuple[list[Proposition], list[Clause]]:
        clause_by_id = {item.clause_id: item for item in clauses}
        quotes = quote_ranges(original_text)
        for profile in self.bare_actions:
            for pattern in profile["compiled_patterns"]:
                for match in pattern.finditer(original_text):
                    match_span = _span(match.start(), match.end(), original_text)
                    if any(
                        item.intent_type == profile["intent_type"]
                        and _overlap(item.source_span, match_span)
                        for item in propositions
                    ):
                        continue
                    clause = _clause_for_position(
                        clauses,
                        match.start(),
                        match.end(),
                    )
                    if clause is None:
                        continue
                    arguments = [Argument(
                        role="agent",
                        value="downstream_system",
                        explicit=False,
                    )]
                    nearest = self._nearest_argument(
                        original_text,
                        clause,
                        match.start(),
                    )
                    if nearest and nearest[1] in {"を", "は"}:
                        arguments.append(self._argument_for_target(
                            nearest[0],
                            nearest[2],
                            original_text,
                            entities,
                            entity_index,
                            explicit=True,
                        ))
                    target_present = bool(self._target_arguments(
                        Proposition(
                            proposition_id="TEMP",
                            predicate=profile["predicate"],
                            intent_type=profile["intent_type"],
                            value=match.group(0),
                            arguments=arguments,
                            source_span=match_span,
                        )
                    ))
                    quoted, quote_source = is_inside_quote(match_span, quotes)
                    speech_act = (
                        "request"
                        if re.search(r"(?:ください|してほしい|してくれ)", match.group(0))
                        else "command"
                    )
                    proposition = Proposition(
                        proposition_id=f"P-{len(propositions) + 1:03d}",
                        predicate=profile["predicate"],
                        surface_predicate=match.group(0),
                        intent_type=profile["intent_type"],
                        value=match.group(0),
                        arguments=arguments,
                        sentence_mood="imperative",
                        speech_act=speech_act,
                        deontic_force="obligation",
                        quoted=quoted,
                        quote_source=quote_source,
                        executable_candidate=target_present and not quoted,
                        clause_id=clause.clause_id,
                        source_span=match_span,
                        status=(
                            ItemStatus.RESOLVED
                            if target_present
                            else ItemStatus.INSUFFICIENT
                        ),
                        evidence_ids=[
                            f"BARE-ACTION:{profile['intent_type']}:{profile['predicate']}"
                        ],
                    )
                    propositions.append(proposition)
                    current = clause_by_id[clause.clause_id]
                    clause_by_id[clause.clause_id] = current.model_copy(update={
                        "proposition_ids": [
                            *current.proposition_ids,
                            proposition.proposition_id,
                        ]
                    })
        return propositions, [clause_by_id[item.clause_id] for item in clauses]

    def _apply_pragmatics(
        self,
        original_text: str,
        clauses: list[Clause],
        propositions: list[Proposition],
        entities: list[Entity],
        entity_index: dict[str, Entity],
        metaphors: list[Metaphor],
    ) -> tuple[list[Proposition], list[Clause], int]:
        clause_by_id = {item.clause_id: item for item in clauses}
        quotes = quote_ranges(original_text)
        count = 0

        def apply(
            span: OriginalSpan,
            *,
            marker: str,
            intent_type: str,
            speech_act: str,
            predicate: str,
            executable: bool,
            epistemic_status: str | None = None,
        ) -> None:
            nonlocal count, propositions
            clause = _clause_for_position(clauses, span.start, span.end)
            text = clause.text if clause else span.source_text
            target, action_intent, action_predicate = self._action_details(text)
            overlapping = [
                (index, item)
                for index, item in enumerate(propositions)
                if _overlap(item.source_span, span)
            ]
            preferred = [
                pair
                for pair in overlapping
                if pair[1].intent_type in ACTION_INTENTS
                or pair[1].intent_type == "question"
            ] or overlapping
            if preferred:
                for index, item in preferred:
                    arguments = list(item.arguments)
                    if target and not any(
                        argument.role in _TARGET_ROLES and argument.value == target
                        for argument in arguments
                    ):
                        arguments.append(self._argument_for_target(
                            target,
                            span,
                            original_text,
                            entities,
                            entity_index,
                            explicit=True,
                        ))
                    effective_intent = (
                        "request"
                        if executable and action_intent
                        else intent_type
                    )
                    effective_predicate = (
                        action_predicate
                        if executable and action_predicate
                        else predicate
                    )
                    allow = bool(
                        executable
                        and target
                        and action_intent
                        and not item.quoted
                    )
                    propositions[index] = item.model_copy(update={
                        "intent_type": effective_intent,
                        "predicate": effective_predicate,
                        "arguments": arguments,
                        "speech_act": speech_act,
                        "sentence_mood": (
                            "interrogative"
                            if speech_act in {
                                "polite_request",
                                "capability_question",
                            }
                            else "declarative"
                        ),
                        "deontic_force": "obligation" if allow else "none",
                        "epistemic_status": epistemic_status or item.epistemic_status,
                        "executable_candidate": allow,
                        "status": (
                            ItemStatus.RESOLVED
                            if not executable or target
                            else ItemStatus.INSUFFICIENT
                        ),
                        "pragmatic_markers": list(dict.fromkeys([
                            *item.pragmatic_markers,
                            marker,
                        ])),
                        "inference_sources": list(dict.fromkeys([
                            *item.inference_sources,
                            f"pragmatic_profile:{marker}",
                        ])),
                    })
                    count += 1
                return

            quoted, quote_source = is_inside_quote(span, quotes)
            arguments: list[Argument] = []
            if target:
                arguments.append(self._argument_for_target(
                    target,
                    span,
                    original_text,
                    entities,
                    entity_index,
                    explicit=True,
                ))
            effective_intent = (
                "request" if executable and action_intent else intent_type
            )
            proposition = Proposition(
                proposition_id=f"P-{len(propositions) + 1:03d}",
                predicate=(
                    action_predicate
                    if executable and action_predicate
                    else predicate
                ),
                surface_predicate=action_predicate,
                intent_type=effective_intent,
                value=span.source_text,
                arguments=arguments,
                sentence_mood=(
                    "interrogative"
                    if speech_act in {
                        "polite_request",
                        "capability_question",
                    }
                    else "declarative"
                ),
                speech_act=speech_act,
                deontic_force=(
                    "obligation"
                    if executable and target and action_intent
                    else "none"
                ),
                epistemic_status=epistemic_status or "asserted",
                quoted=quoted,
                quote_source=quote_source,
                executable_candidate=bool(
                    executable and target and action_intent and not quoted
                ),
                clause_id=clause.clause_id if clause else None,
                source_span=span,
                status=(
                    ItemStatus.RESOLVED
                    if not executable or target
                    else ItemStatus.INSUFFICIENT
                ),
                evidence_ids=[f"PRAGMATIC:{marker}"],
                pragmatic_markers=[marker],
                inference_sources=[f"pragmatic_profile:{marker}"],
            )
            propositions.append(proposition)
            if clause:
                current = clause_by_id[clause.clause_id]
                clause_by_id[clause.clause_id] = current.model_copy(update={
                    "proposition_ids": [
                        *current.proposition_ids,
                        proposition.proposition_id,
                    ]
                })
            count += 1

        seen: set[tuple[int, int, str]] = set()
        for profile in self.pragmatics:
            for pattern in profile["compiled_patterns"]:
                for match in pattern.finditer(original_text):
                    clause = _clause_for_position(
                        clauses,
                        match.start(),
                        match.end(),
                    )
                    span = clause.source_span if clause else _span(
                        match.start(), match.end(), original_text
                    )
                    key = (span.start, span.end, profile["id"])
                    if key in seen:
                        continue
                    seen.add(key)
                    apply(
                        span,
                        marker=profile["id"],
                        intent_type=profile["intent_type"],
                        speech_act=profile["speech_act"],
                        predicate=profile["predicate"],
                        executable=bool(profile.get("executable", False)),
                        epistemic_status=profile.get("epistemic_status"),
                    )

        for metaphor in metaphors:
            mapping = _PRAGMATIC_DOMAIN_MAP.get(metaphor.domain)
            if not mapping:
                continue
            intent_type, speech_act, executable = mapping
            apply(
                metaphor.span,
                marker=f"metaphor_domain:{metaphor.domain}",
                intent_type=intent_type,
                speech_act=speech_act,
                predicate=metaphor.interpretation,
                executable=executable,
            )
        return (
            propositions,
            [clause_by_id[item.clause_id] for item in clauses],
            count,
        )

    def _ensure_sense_observations(
        self,
        original_text: str,
        tokens: list[Token],
        clauses: list[Clause],
        propositions: list[Proposition],
        entities: list[Entity],
        entity_index: dict[str, Entity],
    ) -> tuple[list[Proposition], list[Clause]]:
        clause_by_id = {item.clause_id: item for item in clauses}
        for token in tokens:
            if token.normalized not in self.compiled_senses:
                continue
            if any(
                _overlap(item.source_span, token.span)
                for item in propositions
            ):
                continue
            clause = _clause_for_position(
                clauses,
                token.span.start,
                token.span.end,
            )
            if not clause:
                continue
            arguments: list[Argument] = []
            nearest = self._nearest_argument(
                original_text,
                clause,
                token.span.start,
            )
            if nearest:
                entity_id = self._ensure_entity(
                    entities,
                    entity_index,
                    nearest[0],
                    span=nearest[2],
                    salience=35,
                )
                arguments.append(Argument(
                    role=_CASE_ROLE.get(nearest[1], "object"),
                    value=nearest[0],
                    entity_id=entity_id,
                    case_marker=nearest[1],
                    explicit=True,
                    span=nearest[2],
                ))
            proposition = Proposition(
                proposition_id=f"P-{len(propositions) + 1:03d}",
                predicate=token.normalized,
                surface_predicate=token.surface,
                intent_type="observation",
                value=clause.text,
                arguments=arguments,
                polarity=infer_polarity("observation", clause.text),
                speech_act="assertion",
                epistemic_status=infer_epistemic_status(clause.text),
                executable_candidate=False,
                clause_id=clause.clause_id,
                source_span=token.span,
                evidence_ids=[f"SENSE-LEXEME:{token.normalized}"],
            )
            propositions.append(proposition)
            current = clause_by_id[clause.clause_id]
            clause_by_id[clause.clause_id] = current.model_copy(update={
                "proposition_ids": [
                    *current.proposition_ids,
                    proposition.proposition_id,
                ]
            })
        return propositions, [clause_by_id[item.clause_id] for item in clauses]

    def _sense_for_proposition(
        self,
        proposition: Proposition,
        clause_text: str,
        tokens: list[Token],
    ) -> Proposition:
        candidates_tokens = [
            token
            for token in tokens
            if token.normalized in self.compiled_senses
            and (
                _overlap(token.span, proposition.source_span)
                or (
                    proposition.clause_id
                    and token.span.start <= proposition.source_span.end
                    and token.span.end >= proposition.source_span.start
                )
            )
        ]
        if not candidates_tokens:
            return proposition
        token = candidates_tokens[-1]
        lemma = token.normalized
        profile = self.senses[lemma]
        argument_text = " ".join(
            argument.value for argument in proposition.arguments
        )
        scored: list[SenseCandidate] = []
        for sense in self.compiled_senses[lemma]:
            score = 0
            evidence: list[str] = []
            for cue in sense.get("strong_cues", []):
                if cue in clause_text:
                    score += 6
                    evidence.append(f"strong:{cue}")
                if cue in argument_text:
                    score += 2
                    evidence.append(f"argument:{cue}")
            for cue in sense.get("cues", []):
                if cue in clause_text:
                    score += 3
                    evidence.append(f"cue:{cue}")
            for pattern in sense["compiled_patterns"]:
                if pattern.search(clause_text):
                    score += 8
                    evidence.append(f"pattern:{pattern.pattern}")
            scored.append(SenseCandidate(
                sense_id=sense["id"],
                label=sense["label"],
                score=score,
                evidence=evidence,
            ))
        scored.sort(key=lambda item: (-item.score, item.sense_id))
        positive = [item for item in scored if item.score > 0]
        minimum = int(profile.get("minimum_score", 6))
        margin = int(profile.get("margin", 2))
        if positive:
            top = positive[0]
            second = positive[1].score if len(positive) > 1 else 0
            if top.score >= minimum and top.score - second >= margin:
                confidence = min(1.0, top.score / max(1, top.score + second))
                return proposition.model_copy(update={
                    "surface_predicate": token.surface,
                    "sense_id": top.sense_id,
                    "sense_label": top.label,
                    "sense_confidence": round(confidence, 4),
                    "sense_candidates": positive[:4],
                    "inference_sources": list(dict.fromkeys([
                        *proposition.inference_sources,
                        f"sense_profile:{lemma}",
                    ])),
                })
        updates = {
            "surface_predicate": token.surface,
            "sense_candidates": (positive or scored)[:4],
            "sense_confidence": 0.0,
        }
        if positive and proposition.intent_type in ACTION_INTENTS:
            updates.update({
                "status": ItemStatus.AMBIGUOUS,
                "executable_candidate": False,
                "inference_sources": [
                    *proposition.inference_sources,
                    f"sense_ambiguous:{lemma}",
                ],
            })
        return proposition.model_copy(update=updates)

    @staticmethod
    def _predicate_only(argument: Argument, proposition: Proposition) -> bool:
        if argument.case_marker:
            return False
        compact = _compact(argument.value)
        source = _compact(proposition.source_span.source_text)
        if compact == source:
            return True
        stripped = re.sub(
            r"(?:していただけますか|してもらえませんか|してください|"
            r"してほしい|してくれ|して|しろ|せよ|てください|てくれ|て)$",
            "",
            compact,
        )
        return stripped in set(_ACTION_PREDICATE)

    @staticmethod
    def _valid_antecedent(value: str) -> bool:
        compact = _compact(value)
        return bool(
            compact
            and compact not in _GENERIC_TARGETS
            and compact != "downstream_system"
            and len(compact) >= 2
        )

    def _resolve_ellipsis(
        self,
        propositions: list[Proposition],
        clauses: list[Clause],
        entities: list[Entity],
        entity_index: dict[str, Entity],
        conversation_context: list[str],
        known_entities: list[str],
        unresolved: list[dict],
    ) -> tuple[list[Proposition], list[dict], int]:
        clause_order = {
            item.clause_id: index for index, item in enumerate(clauses)
        }
        history: list[tuple[Proposition, Argument]] = []
        inferred_count = 0
        order = sorted(
            range(len(propositions)),
            key=lambda index: (
                propositions[index].source_span.start,
                propositions[index].source_span.end,
                propositions[index].proposition_id,
            ),
        )
        for index in order:
            proposition = propositions[index]
            if proposition.intent_type not in ACTION_INTENTS:
                continue
            explicit_targets = [
                argument
                for argument in self._target_arguments(proposition)
                if not self._predicate_only(argument, proposition)
                and self._valid_antecedent(argument.value)
            ]
            if explicit_targets:
                history.extend((proposition, item) for item in explicit_targets)
                history = history[-8:]
                continue

            ranked: dict[str, _Antecedent] = {}
            current_clause = clause_order.get(proposition.clause_id or "", 9999)
            for previous, argument in reversed(history):
                if previous.source_span.start >= proposition.source_span.start:
                    continue
                previous_clause = clause_order.get(previous.clause_id or "", 9999)
                distance = proposition.source_span.start - previous.source_span.end
                score = 115 if previous_clause == current_clause else 90
                score -= min(30, max(0, distance) // 8)
                key = _compact(argument.value)
                candidate = _Antecedent(
                    argument.value,
                    argument.entity_id,
                    score,
                    (
                        "same_clause_previous_target"
                        if previous_clause == current_clause
                        else "previous_clause_target"
                    ),
                )
                if key not in ranked or candidate.score > ranked[key].score:
                    ranked[key] = candidate
            for rank, value in enumerate(known_entities):
                if self._valid_antecedent(value):
                    key = _compact(value)
                    ranked.setdefault(key, _Antecedent(
                        value,
                        entity_index.get(key).entity_id if key in entity_index else None,
                        max(55, 75 - rank),
                        "known_entity",
                    ))
            for rank, value in enumerate(reversed(conversation_context)):
                if self._valid_antecedent(value):
                    key = _compact(value)
                    ranked.setdefault(key, _Antecedent(
                        value,
                        entity_index.get(key).entity_id if key in entity_index else None,
                        max(40, 60 - rank),
                        "conversation_context",
                    ))
            values = sorted(ranked.values(), key=lambda item: (-item.score, item.value))
            selected = None
            if values:
                second = values[1].score if len(values) > 1 else 0
                if values[0].score >= 70 and values[0].score - second >= 10:
                    selected = values[0]
            cleaned = [
                item
                for item in proposition.arguments
                if not (
                    item.role in _TARGET_ROLES
                    and self._predicate_only(item, proposition)
                )
            ]
            if selected:
                entity_id = selected.entity_id or self._ensure_entity(
                    entities,
                    entity_index,
                    selected.value,
                    entity_type="ellipsis_antecedent",
                    salience=55,
                )
                inferred = Argument(
                    role="object",
                    value=selected.value,
                    entity_id=entity_id,
                    explicit=False,
                    candidates=[item.value for item in values[:8]],
                    status=ItemStatus.RESOLVED,
                )
                allow = bool(
                    not proposition.quoted
                    and proposition.speech_act in _EXECUTABLE_SPEECH_ACTS
                )
                updated = proposition.model_copy(update={
                    "arguments": [*cleaned, inferred],
                    "status": ItemStatus.RESOLVED,
                    "executable_candidate": allow,
                    "inference_sources": list(dict.fromkeys([
                        *proposition.inference_sources,
                        f"ellipsis:{selected.reason}",
                    ])),
                })
                propositions[index] = updated
                history.append((updated, inferred))
                history = history[-8:]
                unresolved = [
                    item
                    for item in unresolved
                    if item.get("proposition_id") != proposition.proposition_id
                ]
                inferred_count += 1
            elif values:
                propositions[index] = proposition.model_copy(update={
                    "arguments": [*cleaned, Argument(
                        role="object",
                        value=values[0].value,
                        entity_id=values[0].entity_id,
                        explicit=False,
                        candidates=[item.value for item in values[:8]],
                        status=ItemStatus.AMBIGUOUS,
                    )],
                    "status": ItemStatus.AMBIGUOUS,
                    "executable_candidate": False,
                    "inference_sources": [
                        *proposition.inference_sources,
                        "ellipsis:ambiguous",
                    ],
                })
                unresolved.append({
                    "type": "ellipsis_reference",
                    "proposition_id": proposition.proposition_id,
                    "status": ItemStatus.AMBIGUOUS.value,
                    "candidates": [item.value for item in values[:8]],
                    "related_proposition_ids": [proposition.proposition_id],
                })
        return propositions, unresolved, inferred_count

    @staticmethod
    def _observation_for_clause(
        clause: Clause,
        propositions: list[Proposition],
    ) -> Proposition:
        existing = sorted(
            (
                item
                for item in propositions
                if item.clause_id == clause.clause_id
            ),
            key=lambda item: (item.source_span.start, item.proposition_id),
        )
        if existing:
            return existing[0]
        proposition = Proposition(
            proposition_id=f"P-{len(propositions) + 1:03d}",
            predicate="述べる",
            intent_type="observation",
            value=clause.text,
            speech_act="assertion",
            executable_candidate=False,
            clause_id=clause.clause_id,
            source_span=clause.source_span,
            evidence_ids=["DISCOURSE:CLAUSE_OBSERVATION"],
        )
        propositions.append(proposition)
        return proposition

    @staticmethod
    def _discourse_relation(
        previous: str,
        current: str,
        between: str = "",
    ) -> tuple[str, str, float] | None:
        combined = f"{previous}\n{between}\n{current}"
        if re.search(r"^(?:そのため|だから|従って|なので|結果として)", current):
            return "causes", "result_marker", 0.98
        if re.search(r"(?:ので|ため|から)[、。]?\s*$", previous):
            return "causes", "causal_suffix", 0.94
        if re.search(r"^(?:しかし|ただ|一方で?|反面|ところが)", current):
            return "contrasts_with", "contrast_marker", 0.98
        if re.search(r"(?:しかし|けれど|けど|一方で?|反面)", between):
            return "contrasts_with", "contrast_connector", 0.94
        if re.search(r"^(?:つまり|すなわち|具体的には|言い換えると)", current):
            return "elaborates", "elaboration_marker", 0.98
        if re.search(r"^(?:なぜなら|というのも)", current):
            return "justifies", "evidence_marker", 0.98
        if re.search(r"(?:してから|した後|その後|次に|前に)", combined):
            return "precedes", "sequence_marker", 0.92
        if re.search(r"(?:または|もしくは|あるいは)", combined):
            return "alternative_to", "alternative_marker", 0.96
        if re.search(r"(?:ために|ように)", between):
            return "purpose_for", "purpose_marker", 0.92
        if re.search(r"(?:にもかかわらず|のに|ても)", between):
            return "concedes", "concession_marker", 0.92
        return None

    def _add_discourse(
        self,
        original_text: str,
        propositions: list[Proposition],
        clauses: list[Clause],
        edges: list[ScopeEdge],
    ) -> tuple[list[Proposition], list[Clause], list[ScopeEdge], int]:
        clause_by_id = {item.clause_id: item for item in clauses}
        keys = {
            (item.source_id, item.target_id, item.relation)
            for item in edges
        }
        count = 0

        def add(source, target, relation, marker, confidence):
            nonlocal count
            key = (source.proposition_id, target.proposition_id, relation)
            if source.proposition_id == target.proposition_id or key in keys:
                return
            edges.append(ScopeEdge(
                edge_id=f"R-{len(edges) + 1:03d}",
                source_id=source.proposition_id,
                target_id=target.proposition_id,
                relation=relation,
                marker=marker,
                confidence=confidence,
                evidence_ids=[f"DISCOURSE:{marker}"],
            ))
            keys.add(key)
            count += 1

        sorted_clauses = sorted(clauses, key=lambda item: item.source_span.start)
        for previous, current in zip(sorted_clauses, sorted_clauses[1:]):
            relation = self._discourse_relation(previous.text, current.text)
            if not relation:
                continue
            left = self._observation_for_clause(previous, propositions)
            right = self._observation_for_clause(current, propositions)
            name, marker, confidence = relation
            source, target = (right, left) if name == "justifies" else (left, right)
            add(source, target, name, marker, confidence)
            current_clause = clause_by_id[current.clause_id]
            clause_by_id[current.clause_id] = current_clause.model_copy(update={
                "parent_clause_id": previous.clause_id,
                "relation": name,
                "discourse_markers": list(dict.fromkeys([
                    *current_clause.discourse_markers,
                    marker,
                ])),
            })

        for clause in clauses:
            values = sorted(
                (
                    item
                    for item in propositions
                    if item.clause_id == clause.clause_id
                ),
                key=lambda item: item.source_span.start,
            )
            for left, right in zip(values, values[1:]):
                between = original_text[left.source_span.end:right.source_span.start]
                relation = self._discourse_relation(
                    left.source_span.source_text,
                    right.source_span.source_text,
                    between,
                )
                if relation:
                    add(left, right, *relation)

        alternative = re.search(
            r"(?P<left>[^、。！？!?]{1,32})(?:または|もしくは|あるいは)"
            r"(?P<right>[^、。！？!?]{1,32})",
            original_text,
        )
        if alternative and not any(
            item.relation == "alternative_to" for item in edges
        ):
            left_text = clean_fragment(alternative.group("left"))
            right_text = clean_fragment(alternative.group("right"))
            if left_text and right_text:
                left_start = alternative.start("left")
                right_start = alternative.start("right")
                left = Proposition(
                    proposition_id=f"P-{len(propositions) + 1:03d}",
                    predicate="選択肢である",
                    intent_type="observation",
                    value=left_text,
                    source_span=_span(
                        left_start,
                        left_start + len(alternative.group("left")),
                        original_text,
                    ),
                    evidence_ids=["DISCOURSE:ALTERNATIVE_LEFT"],
                )
                propositions.append(left)
                right = Proposition(
                    proposition_id=f"P-{len(propositions) + 1:03d}",
                    predicate="選択肢である",
                    intent_type="observation",
                    value=right_text,
                    source_span=_span(
                        right_start,
                        right_start + len(alternative.group("right")),
                        original_text,
                    ),
                    evidence_ids=["DISCOURSE:ALTERNATIVE_RIGHT"],
                )
                propositions.append(right)
                add(left, right, "alternative_to", "alternative_marker", 0.96)

        for clause in clauses:
            missing = [
                item.proposition_id
                for item in propositions
                if item.clause_id == clause.clause_id
                and item.proposition_id not in clause.proposition_ids
            ]
            if missing:
                current = clause_by_id[clause.clause_id]
                clause_by_id[clause.clause_id] = current.model_copy(update={
                    "proposition_ids": [*current.proposition_ids, *missing]
                })
        return (
            propositions,
            [clause_by_id[item.clause_id] for item in clauses],
            edges,
            count,
        )

    def enrich(
        self,
        graph: MeaningGraph,
        *,
        original_text: str,
        tokens: list[Token],
        metaphors: list[Metaphor],
        conversation_context: list[str],
        known_entities: list[str],
    ) -> MeaningGraph:
        propositions = list(graph.propositions)
        clauses = list(graph.clauses)
        entities = list(graph.entities)
        edges = list(graph.scope_edges)
        unresolved = list(graph.unresolved)
        entity_index = self._entity_index(entities)

        propositions, clauses = self._create_bare_actions(
            original_text,
            clauses,
            propositions,
            entities,
            entity_index,
        )
        propositions, clauses, pragmatic_count = self._apply_pragmatics(
            original_text,
            clauses,
            propositions,
            entities,
            entity_index,
            metaphors,
        )
        propositions, clauses = self._ensure_sense_observations(
            original_text,
            tokens,
            clauses,
            propositions,
            entities,
            entity_index,
        )

        clause_text = {item.clause_id: item.text for item in clauses}
        resolved_senses = 0
        ambiguous_senses = 0
        for index, proposition in enumerate(propositions):
            updated = self._sense_for_proposition(
                proposition,
                clause_text.get(
                    proposition.clause_id or "",
                    proposition.source_span.source_text,
                ),
                tokens,
            )
            propositions[index] = updated
            if updated.sense_id:
                resolved_senses += 1
            elif updated.sense_candidates:
                ambiguous_senses += 1
                if updated.intent_type in ACTION_INTENTS:
                    unresolved.append({
                        "type": "sense_ambiguity",
                        "proposition_id": updated.proposition_id,
                        "status": ItemStatus.AMBIGUOUS.value,
                        "candidates": [
                            item.model_dump(mode="json")
                            for item in updated.sense_candidates
                        ],
                        "related_proposition_ids": [updated.proposition_id],
                    })

        propositions, unresolved, inferred_count = self._resolve_ellipsis(
            propositions,
            clauses,
            entities,
            entity_index,
            conversation_context,
            known_entities,
            unresolved,
        )
        propositions, clauses, edges, discourse_count = self._add_discourse(
            original_text,
            propositions,
            clauses,
            edges,
        )
        graph = graph.model_copy(update={
            "entities": entities,
            "clauses": clauses,
            "propositions": sorted(
                propositions,
                key=lambda item: (
                    item.source_span.start,
                    item.source_span.end,
                    item.proposition_id,
                ),
            ),
            "scope_edges": edges,
            "unresolved": unresolved,
            "quality_annotations": {
                "semantic_profile_version": self.doc.get("version", "0"),
                "resolved_senses": resolved_senses,
                "ambiguous_senses": ambiguous_senses,
                "inferred_arguments": inferred_count,
                "pragmatic_acts": pragmatic_count,
                "discourse_edges": discourse_count,
            },
        })
        graph = graph.model_copy(update={"semantic_hash": _stable_hash(graph)})
        self.last_metrics = {
            "resolved_sense_count": resolved_senses,
            "ambiguous_sense_count": ambiguous_senses,
            "inferred_argument_count": inferred_count,
            "pragmatic_act_count": pragmatic_count,
            "discourse_edge_count": discourse_count,
        }
        return graph
