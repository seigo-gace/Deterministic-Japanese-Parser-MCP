from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable

import yaml

from .canonical import Canonicalizer
from .grammar_kernel import (
    ACTION_INTENTS,
    clean_fragment,
    infer_deontic_force,
    infer_epistemic_status,
    infer_polarity,
    infer_sentence_mood,
    infer_speech_act,
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
    best: Clause | None = None
    best_overlap = -1
    for clause in clauses:
        current = max(
            0,
            min(end, clause.source_span.end)
            - max(start, clause.source_span.start),
        )
        if current > best_overlap:
            best = clause
            best_overlap = current
    return best


def _target_arguments(proposition: Proposition) -> list[Argument]:
    return [
        item
        for item in proposition.arguments
        if item.role in _TARGET_ROLES and item.value
    ]


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
    """Deterministically enrich a Meaning Graph without generative inference.

    The layer performs only bounded, evidence-backed operations:

    - high-impact lexical sense selection from curated cue profiles;
    - omitted target recovery from explicit local antecedents;
    - indirect speech-act classification and action suppression;
    - discourse relation construction between propositions and clauses.

    Ambiguous evidence remains explicit and external actions fail closed.
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
            value["compiled_patterns"] = [
                re.compile(pattern)
                for pattern in item.get("patterns", [])
            ]
            self.pragmatics.append(value)

        self.bare_actions: list[dict] = []
        for item in self.doc.get("bare_actions", []):
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
        entity_type: str = "inferred_entity",
        salience: int = 25,
    ) -> str | None:
        value = clean_fragment(value)
        key = _compact(value)
        if not key:
            return None
        existing = index.get(key)
        if existing is not None:
            updates: dict = {}
            if value not in existing.mentions:
                updates["mentions"] = [*existing.mentions, value]
            if span is not None and all(
                not (
                    item.start == span.start
                    and item.end == span.end
                )
                for item in existing.source_spans
            ):
                updates["source_spans"] = [*existing.source_spans, span]
            if salience > existing.salience:
                updates["salience"] = salience
            if updates:
                replacement = existing.model_copy(update=updates)
                entities[entities.index(existing)] = replacement
                for alias in [replacement.canonical, *replacement.mentions]:
                    index[_compact(alias)] = replacement
                existing = replacement
            return existing.entity_id

        entity = Entity(
            entity_id=f"E-{len(entities) + 1:03d}",
            canonical=value,
            entity_type=entity_type,
            mentions=[value],
            source_spans=[span] if span is not None else [],
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
        prefix = re.split(r"[、。！？!?]", prefix)[-1].strip()
        match = re.search(
            r"(?P<value>[^、。！？!?]{1,48}?)(?P<marker>から|まで|より|を|は|が|に|へ|で|と)$",
            prefix,
        )
        if not match:
            return None
        value = clean_fragment(match.group("value"))
        marker = match.group("marker")
        if not value:
            return None
        absolute_start = (
            clause.source_span.start
            + prefix.rfind(match.group("value"))
        )
        argument_span = _span(
            absolute_start,
            absolute_start + len(match.group("value")),
            original_text,
        )
        return value, marker, argument_span

    def _create_observations(
        self,
        original_text: str,
        tokens: list[Token],
        clauses: list[Clause],
        propositions: list[Proposition],
        entities: list[Entity],
        entity_index: dict[str, Entity],
    ) -> tuple[list[Proposition], list[Clause]]:
        proposition_spans = [item.source_span for item in propositions]
        clause_by_id = {item.clause_id: item for item in clauses}
        for token in tokens:
            lemma = token.normalized
            if lemma not in self.compiled_senses:
                continue
            if any(_overlap(token.span, span) for span in proposition_spans):
                continue
            clause = _clause_for_position(
                clauses,
                token.span.start,
                token.span.end,
            )
            if clause is None:
                continue
            arguments: list[Argument] = []
            nearest = self._nearest_argument(
                original_text,
                clause,
                token.span.start,
            )
            if nearest is not None:
                value, marker, argument_span = nearest
                entity_id = self._ensure_entity(
                    entities,
                    entity_index,
                    value,
                    span=argument_span,
                    salience=35,
                )
                arguments.append(Argument(
                    role=_CASE_ROLE.get(marker, "object"),
                    value=value,
                    entity_id=entity_id,
                    case_marker=marker,
                    explicit=True,
                    span=argument_span,
                ))
            proposition = Proposition(
                proposition_id=f"P-{len(propositions) + 1:03d}",
                predicate=lemma,
                surface_predicate=token.surface,
                intent_type="observation",
                value=clause.text,
                arguments=arguments,
                polarity=infer_polarity("observation", clause.text),
                sentence_mood="declarative",
                speech_act="assertion",
                deontic_force="none",
                epistemic_status=infer_epistemic_status(clause.text),
                quoted=False,
                executable_candidate=False,
                clause_id=clause.clause_id,
                source_span=token.span,
                status=ItemStatus.RESOLVED,
                evidence_ids=[f"SENSE-LEXEME:{lemma}"],
            )
            propositions.append(proposition)
            proposition_spans.append(token.span)
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
        covered = [
            item
            for item in tokens
            if proposition.source_span.start <= item.span.start
            and item.span.end <= proposition.source_span.end
            and item.normalized in self.compiled_senses
        ]
        if not covered and proposition.surface_predicate:
            covered = [
                item
                for item in tokens
                if item.surface == proposition.surface_predicate
                and item.normalized in self.compiled_senses
            ]
        if not covered:
            return proposition
        token = covered[-1]
        lemma = token.normalized
        profile = self.senses[lemma]
        argument_text = " ".join(
            item.value for item in proposition.arguments if item.value
        )
        candidates: list[SenseCandidate] = []
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
            for pattern in sense.get("compiled_patterns", []):
                if pattern.search(clause_text):
                    score += 8
                    evidence.append(f"pattern:{pattern.pattern}")
            for cue in sense.get("negative_cues", []):
                if cue in clause_text:
                    score -= 6
                    evidence.append(f"negative:{cue}")
            candidates.append(SenseCandidate(
                sense_id=sense["id"],
                label=sense["label"],
                score=score,
                evidence=evidence,
            ))
        candidates.sort(key=lambda item: (-item.score, item.sense_id))
        positive = [item for item in candidates if item.score > 0]
        minimum = int(profile.get("minimum_score", 6))
        margin = int(profile.get("margin", 2))
        selected: SenseCandidate | None = None
        if positive:
            top = positive[0]
            second = positive[1].score if len(positive) > 1 else 0
            if top.score >= minimum and top.score - second >= margin:
                selected = top
        if selected is not None:
            confidence = min(
                1.0,
                selected.score
                / max(1, selected.score + (positive[1].score if len(positive) > 1 else 0)),
            )
            return proposition.model_copy(update={
                "surface_predicate": token.surface,
                "sense_id": selected.sense_id,
                "sense_label": selected.label,
                "sense_confidence": round(confidence, 4),
                "sense_candidates": positive[:4],
                "inference_sources": [
                    *proposition.inference_sources,
                    f"sense_profile:{lemma}",
                ],
            })
        if not positive:
            return proposition.model_copy(update={
                "surface_predicate": token.surface,
                "sense_candidates": candidates[:4],
                "sense_confidence": 0.0,
            })
        updates: dict = {
            "surface_predicate": token.surface,
            "sense_candidates": positive[:4],
            "sense_confidence": 0.0,
            "inference_sources": [
                *proposition.inference_sources,
                f"sense_ambiguous:{lemma}",
            ],
        }
        if proposition.intent_type in ACTION_INTENTS:
            updates["status"] = ItemStatus.AMBIGUOUS
            updates["executable_candidate"] = False
        return proposition.model_copy(update=updates)

    @staticmethod
    def _pragmatic_span(
        match: re.Match,
        original_text: str,
        clauses: list[Clause],
    ) -> OriginalSpan:
        clause = _clause_for_position(
            clauses,
            match.start(),
            match.end(),
        )
        if clause is not None:
            return clause.source_span
        return _span(match.start(), match.end(), original_text)

    @staticmethod
    def _extract_request_target(
        clause_text: str,
    ) -> tuple[str | None, str | None]:
        match = re.search(
            r"(?P<target>[^、。！？!?]{1,48}?)(?:を|は)?"
            r"(?P<action>確認|共有|修正|変更|更新|削除|公開|保存|送信|実行|検証|テスト)"
            r"(?:して|していただけ|してもらえ|してください|してほしい)",
            clause_text,
        )
        if not match:
            return None, None
        target = clean_fragment(match.group("target"))
        return (target or None), match.group("action")

    @staticmethod
    def _predicate_for_action(action: str | None) -> str:
        return {
            "確認": "確認する",
            "共有": "共有する",
            "修正": "変更する",
            "変更": "変更する",
            "更新": "変更する",
            "削除": "削除する",
            "公開": "公開する",
            "保存": "保存する",
            "送信": "送信する",
            "実行": "実行する",
            "検証": "検証する",
            "テスト": "検証する",
        }.get(action or "", "要求する")

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
        pragmatic_count = 0

        def apply(
            span: OriginalSpan,
            *,
            marker_id: str,
            intent_type: str,
            speech_act: str,
            predicate: str,
            executable: bool,
            epistemic_status: str | None = None,
        ) -> None:
            nonlocal propositions, pragmatic_count
            overlapping = [
                (index, item)
                for index, item in enumerate(propositions)
                if _overlap(item.source_span, span)
            ]
            action_overlapping = [
                pair
                for pair in overlapping
                if pair[1].intent_type in ACTION_INTENTS
            ]
            targets = action_overlapping or overlapping
            if targets:
                for index, item in targets:
                    allow = (
                        executable
                        and item.intent_type in ACTION_INTENTS
                        and item.status == ItemStatus.RESOLVED
                        and not item.quoted
                    )
                    propositions[index] = item.model_copy(update={
                        "speech_act": speech_act,
                        "epistemic_status": (
                            epistemic_status or item.epistemic_status
                        ),
                        "executable_candidate": allow,
                        "pragmatic_markers": list(dict.fromkeys([
                            *item.pragmatic_markers,
                            marker_id,
                        ])),
                        "inference_sources": list(dict.fromkeys([
                            *item.inference_sources,
                            f"pragmatic_profile:{marker_id}",
                        ])),
                    })
                    pragmatic_count += 1
                return

            clause = _clause_for_position(
                clauses,
                span.start,
                span.end,
            )
            target, action = self._extract_request_target(
                clause.text if clause else span.source_text
            )
            arguments: list[Argument] = []
            if target:
                target_start = original_text.find(
                    target,
                    span.start,
                    span.end,
                )
                target_span = (
                    _span(target_start, target_start + len(target), original_text)
                    if target_start >= 0
                    else None
                )
                entity_id = self._ensure_entity(
                    entities,
                    entity_index,
                    target,
                    span=target_span,
                    salience=40,
                )
                arguments.append(Argument(
                    role="object",
                    value=target,
                    entity_id=entity_id,
                    case_marker="を",
                    explicit=True,
                    span=target_span,
                ))
            quoted, quote_source = is_inside_quote(
                span,
                quote_ranges(original_text),
            )
            effective_intent = (
                "request"
                if executable and action
                else intent_type
            )
            proposition = Proposition(
                proposition_id=f"P-{len(propositions) + 1:03d}",
                predicate=(
                    self._predicate_for_action(action)
                    if executable and action
                    else predicate
                ),
                surface_predicate=action,
                intent_type=effective_intent,
                value=span.source_text,
                arguments=arguments,
                polarity=infer_polarity(effective_intent, span.source_text),
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
                    if executable and action
                    else "none"
                ),
                epistemic_status=epistemic_status or "asserted",
                quoted=quoted,
                quote_source=quote_source,
                executable_candidate=(
                    executable
                    and bool(action)
                    and bool(target)
                    and not quoted
                ),
                clause_id=clause.clause_id if clause else None,
                source_span=span,
                status=(
                    ItemStatus.RESOLVED
                    if not executable or target
                    else ItemStatus.INSUFFICIENT
                ),
                evidence_ids=[f"PRAGMATIC:{marker_id}"],
                pragmatic_markers=[marker_id],
                inference_sources=[f"pragmatic_profile:{marker_id}"],
            )
            propositions.append(proposition)
            if clause is not None:
                current = clause_by_id[clause.clause_id]
                clause_by_id[clause.clause_id] = current.model_copy(update={
                    "proposition_ids": [
                        *current.proposition_ids,
                        proposition.proposition_id,
                    ]
                })
            pragmatic_count += 1

        matched_ranges: set[tuple[int, int, str]] = set()
        for profile in self.pragmatics:
            for pattern in profile.get("compiled_patterns", []):
                for match in pattern.finditer(original_text):
                    key = (match.start(), match.end(), profile["id"])
                    if key in matched_ranges:
                        continue
                    matched_ranges.add(key)
                    apply(
                        self._pragmatic_span(match, original_text, clauses),
                        marker_id=profile["id"],
                        intent_type=profile["intent_type"],
                        speech_act=profile["speech_act"],
                        predicate=profile["predicate"],
                        executable=bool(profile.get("executable", False)),
                        epistemic_status=profile.get("epistemic_status"),
                    )

        for metaphor in metaphors:
            mapping = _PRAGMATIC_DOMAIN_MAP.get(metaphor.domain)
            if mapping is None:
                continue
            intent_type, speech_act, executable = mapping
            apply(
                metaphor.span,
                marker_id=f"metaphor_domain:{metaphor.domain}",
                intent_type=intent_type,
                speech_act=speech_act,
                predicate=metaphor.interpretation,
                executable=executable,
            )

        return (
            propositions,
            [clause_by_id[item.clause_id] for item in clauses],
            pragmatic_count,
        )

    @staticmethod
    def _already_has_action(
        propositions: list[Proposition],
        span: OriginalSpan,
        intent_type: str,
    ) -> bool:
        return any(
            item.intent_type == intent_type
            and _overlap(item.source_span, span)
            for item in propositions
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
            for pattern in profile.get("compiled_patterns", []):
                for match in pattern.finditer(original_text):
                    match_span = _span(match.start(), match.end(), original_text)
                    if self._already_has_action(
                        propositions,
                        match_span,
                        profile["intent_type"],
                    ):
                        continue
                    clause = _clause_for_position(
                        clauses,
                        match.start(),
                        match.end(),
                    )
                    if clause is None:
                        continue
                    arguments: list[Argument] = [Argument(
                        role="agent",
                        value="downstream_system",
                        explicit=False,
                    )]
                    nearest = self._nearest_argument(
                        original_text,
                        clause,
                        match.start(),
                    )
                    if nearest is not None:
                        value, marker, argument_span = nearest
                        if marker in {"を", "は"}:
                            entity_id = self._ensure_entity(
                                entities,
                                entity_index,
                                value,
                                span=argument_span,
                                salience=45,
                            )
                            arguments.append(Argument(
                                role="object",
                                value=value,
                                entity_id=entity_id,
                                case_marker=marker,
                                explicit=True,
                                span=argument_span,
                            ))
                    target_present = any(
                        item.role in _TARGET_ROLES and item.value
                        for item in arguments
                    )
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
                        polarity="positive",
                        sentence_mood="imperative",
                        speech_act=speech_act,
                        deontic_force="obligation",
                        epistemic_status="asserted",
                        quoted=quoted,
                        quote_source=quote_source,
                        executable_candidate=(
                            target_present and not quoted
                        ),
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

    @staticmethod
    def _predicate_only(argument: Argument, proposition: Proposition) -> bool:
        if argument.case_marker:
            return False
        compact = _compact(argument.value)
        source = _compact(proposition.source_span.source_text)
        if not compact:
            return True
        if compact == source and len(compact) <= 24:
            return True
        stripped = re.sub(
            r"(?:していただけますか|してもらえませんか|してください|"
            r"してほしい|してくれ|して|しろ|せよ|てください|てくれ|て)$",
            "",
            compact,
        )
        return stripped in {
            "修正",
            "変更",
            "更新",
            "書き換え",
            "削除",
            "消去",
            "確認",
            "保存",
            "共有",
            "テスト",
            "検証",
            "公開",
            "送信",
            "再起動",
            "実行",
        }

    @staticmethod
    def _valid_antecedent(value: str) -> bool:
        compact = _compact(value)
        return bool(
            compact
            and compact not in _GENERIC_TARGETS
            and len(compact) >= 2
            and compact != "downstream_system"
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
    ) -> tuple[list[Proposition], list[Entity], list[dict], int]:
        clause_order = {
            item.clause_id: index for index, item in enumerate(clauses)
        }
        ordered = sorted(
            enumerate(propositions),
            key=lambda item: (
                item[1].source_span.start,
                item[1].source_span.end,
                item[1].proposition_id,
            ),
        )
        last_targets: list[tuple[Proposition, Argument]] = []
        inferred_count = 0

        for original_index, proposition in ordered:
            if proposition.intent_type not in ACTION_INTENTS:
                continue
            valid_targets = [
                item
                for item in _target_arguments(proposition)
                if not self._predicate_only(item, proposition)
                and self._valid_antecedent(item.value)
            ]
            if valid_targets:
                for item in valid_targets:
                    last_targets.append((proposition, item))
                last_targets = last_targets[-8:]
                continue

            antecedents: dict[str, _Antecedent] = {}
            current_clause = clause_order.get(proposition.clause_id or "", 9999)
            for previous, argument in reversed(last_targets):
                if previous.source_span.start >= proposition.source_span.start:
                    continue
                previous_clause = clause_order.get(previous.clause_id or "", 9999)
                distance = max(
                    0,
                    proposition.source_span.start
                    - previous.source_span.end,
                )
                score = 110 if previous_clause == current_clause else 85
                score -= min(30, distance // 8)
                key = _compact(argument.value)
                candidate = _Antecedent(
                    value=argument.value,
                    entity_id=argument.entity_id,
                    score=score,
                    reason=(
                        "same_clause_previous_target"
                        if previous_clause == current_clause
                        else "previous_clause_target"
                    ),
                )
                existing = antecedents.get(key)
                if existing is None or candidate.score > existing.score:
                    antecedents[key] = candidate

            for rank, value in enumerate(known_entities):
                if not self._valid_antecedent(value):
                    continue
                key = _compact(value)
                antecedents.setdefault(key, _Antecedent(
                    value=value,
                    entity_id=(entity_index.get(key).entity_id if key in entity_index else None),
                    score=max(40, 65 - rank),
                    reason="known_entity",
                ))
            for rank, value in enumerate(reversed(conversation_context)):
                if not self._valid_antecedent(value):
                    continue
                key = _compact(value)
                antecedents.setdefault(key, _Antecedent(
                    value=value,
                    entity_id=(entity_index.get(key).entity_id if key in entity_index else None),
                    score=max(30, 55 - rank),
                    reason="conversation_context",
                ))

            ranked = sorted(
                antecedents.values(),
                key=lambda item: (-item.score, item.value),
            )
            selected: _Antecedent | None = None
            if ranked:
                second = ranked[1].score if len(ranked) > 1 else 0
                if ranked[0].score >= 70 and ranked[0].score - second >= 10:
                    selected = ranked[0]
            cleaned_arguments = [
                item
                for item in proposition.arguments
                if not (
                    item.role in _TARGET_ROLES
                    and self._predicate_only(item, proposition)
                )
            ]
            if selected is not None:
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
                    candidates=[item.value for item in ranked[:8]],
                    status=ItemStatus.RESOLVED,
                )
                allow = (
                    not proposition.quoted
                    and proposition.speech_act in _EXECUTABLE_SPEECH_ACTS
                )
                updated = proposition.model_copy(update={
                    "arguments": [*cleaned_arguments, inferred],
                    "status": ItemStatus.RESOLVED,
                    "executable_candidate": allow,
                    "inference_sources": list(dict.fromkeys([
                        *proposition.inference_sources,
                        f"ellipsis:{selected.reason}",
                    ])),
                })
                propositions[original_index] = updated
                last_targets.append((updated, inferred))
                last_targets = last_targets[-8:]
                unresolved = [
                    item
                    for item in unresolved
                    if not (
                        item.get("proposition_id")
                        == proposition.proposition_id
                        and item.get("type") == "proposition"
                    )
                ]
                inferred_count += 1
            elif ranked:
                ambiguous = Argument(
                    role="object",
                    value=ranked[0].value,
                    entity_id=ranked[0].entity_id,
                    explicit=False,
                    candidates=[item.value for item in ranked[:8]],
                    status=ItemStatus.AMBIGUOUS,
                )
                propositions[original_index] = proposition.model_copy(update={
                    "arguments": [*cleaned_arguments, ambiguous],
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
                    "candidates": [item.value for item in ranked[:8]],
                    "related_proposition_ids": [proposition.proposition_id],
                })
        return propositions, entities, unresolved, inferred_count

    @staticmethod
    def _ensure_clause_observation(
        clause: Clause,
        propositions: list[Proposition],
    ) -> Proposition:
        existing = [
            item
            for item in propositions
            if item.clause_id == clause.clause_id
        ]
        if existing:
            return sorted(
                existing,
                key=lambda item: (
                    item.source_span.start,
                    item.proposition_id,
                ),
            )[0]
        proposition = Proposition(
            proposition_id=f"P-{len(propositions) + 1:03d}",
            predicate="述べる",
            intent_type="observation",
            value=clause.text,
            sentence_mood="declarative",
            speech_act="assertion",
            deontic_force="none",
            epistemic_status=infer_epistemic_status(clause.text),
            executable_candidate=False,
            clause_id=clause.clause_id,
            source_span=clause.source_span,
            status=ItemStatus.RESOLVED,
            evidence_ids=["DISCOURSE:CLAUSE_OBSERVATION"],
        )
        propositions.append(proposition)
        return proposition

    def _discourse_relation(
        self,
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
        if re.search(r"(?:してから|した後|その後|次に)", combined):
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
        propositions: list[Proposition],
        clauses: list[Clause],
        edges: list[ScopeEdge],
    ) -> tuple[list[Proposition], list[Clause], list[ScopeEdge], int]:
        clause_by_id = {item.clause_id: item for item in clauses}
        edge_keys = {
            (item.source_id, item.target_id, item.relation)
            for item in edges
        }
        added = 0

        def add(
            source: Proposition,
            target: Proposition,
            relation: str,
            marker: str,
            confidence: float,
        ) -> None:
            nonlocal added
            key = (source.proposition_id, target.proposition_id, relation)
            if key in edge_keys or source.proposition_id == target.proposition_id:
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
            edge_keys.add(key)
            added += 1

        sorted_clauses = sorted(
            clauses,
            key=lambda item: item.source_span.start,
        )
        for previous, current in zip(sorted_clauses, sorted_clauses[1:]):
            relation = self._discourse_relation(
                previous.text,
                current.text,
            )
            if relation is None:
                continue
            previous_prop = self._ensure_clause_observation(
                previous,
                propositions,
            )
            current_prop = self._ensure_clause_observation(
                current,
                propositions,
            )
            relation_name, marker, confidence = relation
            source, target = previous_prop, current_prop
            if relation_name == "justifies":
                source, target = current_prop, previous_prop
            add(source, target, relation_name, marker, confidence)
            current_clause = clause_by_id[current.clause_id]
            clause_by_id[current.clause_id] = current_clause.model_copy(update={
                "parent_clause_id": previous.clause_id,
                "relation": relation_name,
                "discourse_markers": list(dict.fromkeys([
                    *current_clause.discourse_markers,
                    marker,
                ])),
            })

        by_clause: dict[str, list[Proposition]] = {}
        for proposition in propositions:
            if proposition.clause_id:
                by_clause.setdefault(proposition.clause_id, []).append(proposition)
        for clause in clauses:
            values = sorted(
                by_clause.get(clause.clause_id, []),
                key=lambda item: item.source_span.start,
            )
            for left, right in zip(values, values[1:]):
                between = clause.text[
                    max(0, left.source_span.end - clause.source_span.start):
                    max(0, right.source_span.start - clause.source_span.start)
                ]
                relation = self._discourse_relation(
                    left.source_span.source_text,
                    right.source_span.source_text,
                    between,
                )
                if relation is None:
                    continue
                relation_name, marker, confidence = relation
                add(left, right, relation_name, marker, confidence)

        final_clauses = [
            clause_by_id[item.clause_id]
            for item in clauses
        ]
        proposition_ids = {item.proposition_id for item in propositions}
        for clause in final_clauses:
            missing = [
                item.proposition_id
                for item in propositions
                if item.clause_id == clause.clause_id
                and item.proposition_id not in clause.proposition_ids
            ]
            if missing:
                clause_by_id[clause.clause_id] = clause.model_copy(update={
                    "proposition_ids": [
                        *clause.proposition_ids,
                        *missing,
                    ]
                })
        final_clauses = [clause_by_id[item.clause_id] for item in clauses]
        assert proposition_ids == {
            item.proposition_id for item in propositions
        }
        return propositions, final_clauses, edges, added

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

        propositions, clauses = self._create_observations(
            original_text,
            tokens,
            clauses,
            propositions,
            entities,
            entity_index,
        )
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

        clause_text = {
            item.clause_id: item.text for item in clauses
        }
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
                            item.model_dump()
                            for item in updated.sense_candidates
                        ],
                        "related_proposition_ids": [updated.proposition_id],
                    })

        (
            propositions,
            entities,
            unresolved,
            inferred_count,
        ) = self._resolve_ellipsis(
            propositions,
            clauses,
            entities,
            entity_index,
            conversation_context,
            known_entities,
            unresolved,
        )
        propositions, clauses, edges, discourse_count = self._add_discourse(
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
