from __future__ import annotations

import hashlib
import json
import re
from typing import Callable

from .grammar_kernel import ACTION_INTENTS, clean_fragment
from .models import (
    Argument,
    Entity,
    ItemStatus,
    MeaningGraph,
    OriginalSpan,
    Proposition,
    ScopeEdge,
    SenseCandidate,
)
from .semantic_enrichment import SemanticEnricher

_ALIAS_LEMMAS = {
    "開ける": "開く",
    "立ち上がる": "立つ",
}
_ACTION_SURFACES = {
    "変更する": ["修正", "変更", "更新", "書き換え", "直し"],
    "削除する": ["削除", "消去", "消し", "外し"],
    "確認する": ["確認"],
    "保存する": ["保存"],
    "共有する": ["共有"],
    "公開する": ["公開"],
    "送信する": ["送信"],
    "実行する": ["実行"],
    "検証する": ["検証", "テスト"],
    "再起動する": ["再起動"],
}
_GENERIC_TARGETS = {
    "これ",
    "それ",
    "内容",
    "対応",
    "作業",
    "処理",
    "問題",
    "実行",
    "確認",
    "修正",
    "変更",
    "削除",
    "公開",
    "保存",
    "共有",
}
_OBJECT_PATTERN = re.compile(
    r"(?P<value>[^、。！？!?]{1,40}?)(?:を|は)"
    r"(?=[^、。！？!?]{0,28}(?:して|し|て|取|作成|選択|停止|開|"
    r"確認|修正|変更|更新|共有|保存|削除|再起動|実行|検証|テスト))"
)


def _compact(value: str) -> str:
    return re.sub(r"[\s、。！？!?「」『』\"'()（）]+", "", value or "")


def _hash(graph: MeaningGraph) -> str:
    payload = graph.model_dump(exclude={"semantic_hash"}, mode="json")
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _clause(graph: MeaningGraph, start: int):
    candidates = [
        item
        for item in graph.clauses
        if item.source_span.start <= start < item.source_span.end
    ]
    return min(
        candidates,
        key=lambda item: item.source_span.end - item.source_span.start,
        default=None,
    )


def _entity_index(graph: MeaningGraph) -> dict[str, Entity]:
    output: dict[str, Entity] = {}
    for entity in graph.entities:
        for value in [entity.canonical, *entity.mentions, *entity.aliases]:
            key = _compact(value)
            if key:
                output.setdefault(key, entity)
    return output


def _ensure_entity(
    graph: MeaningGraph,
    index: dict[str, Entity],
    value: str,
    *,
    entity_type: str,
) -> tuple[MeaningGraph, str]:
    value = clean_fragment(value)
    key = _compact(value)
    existing = index.get(key)
    if existing is not None:
        return graph, existing.entity_id
    entity = Entity(
        entity_id=f"E-{len(graph.entities) + 1:03d}",
        canonical=value,
        entity_type=entity_type,
        mentions=[value],
        salience=55,
        status=ItemStatus.RESOLVED,
    )
    graph = graph.model_copy(update={
        "entities": [*graph.entities, entity],
    })
    index[key] = entity
    return graph, entity.entity_id


def _score_sense(profile: dict, clause_text: str) -> list[SenseCandidate]:
    output: list[SenseCandidate] = []
    for sense in profile.get("senses", []):
        score = 0
        evidence: list[str] = []
        for cue in sense.get("strong_cues", []):
            if cue in clause_text:
                score += 6
                evidence.append(f"strong:{cue}")
        for cue in sense.get("cues", []):
            if cue in clause_text:
                score += 3
                evidence.append(f"cue:{cue}")
        for raw in sense.get("patterns", []):
            if re.search(raw, clause_text):
                score += 8
                evidence.append(f"pattern:{raw}")
        output.append(SenseCandidate(
            sense_id=sense["id"],
            label=sense["label"],
            score=score,
            evidence=evidence,
        ))
    return sorted(output, key=lambda item: (-item.score, item.sense_id))


def _refine_senses(
    enricher: SemanticEnricher,
    graph: MeaningGraph,
    *,
    original_text: str,
    tokens,
) -> tuple[MeaningGraph, int]:
    propositions = list(graph.propositions)
    clauses = {item.clause_id: item for item in graph.clauses}
    fixed = 0
    for token in tokens:
        lemma = _ALIAS_LEMMAS.get(token.normalized, token.normalized)
        profile = enricher.doc.get("senses", {}).get(lemma)
        if profile is None:
            continue
        clause = _clause(graph, token.span.start)
        if clause is None:
            continue
        matching = [
            index
            for index, item in enumerate(propositions)
            if item.clause_id == clause.clause_id
            and (
                item.source_span.start <= token.span.start <= item.source_span.end
                or item.intent_type == "observation"
            )
        ]
        if matching and any(propositions[index].sense_id for index in matching):
            continue
        scored = _score_sense(profile, clause.text)
        positive = [item for item in scored if item.score > 0]
        minimum = int(profile.get("minimum_score", 6))
        margin = int(profile.get("margin", 2))
        selected = None
        if positive:
            second = positive[1].score if len(positive) > 1 else 0
            if positive[0].score >= minimum and positive[0].score - second >= margin:
                selected = positive[0]
        if matching:
            index = matching[-1]
            proposition = propositions[index]
        else:
            proposition = Proposition(
                proposition_id=f"P-{len(propositions) + 1:03d}",
                predicate=lemma,
                surface_predicate=token.surface,
                intent_type="observation",
                value=clause.text,
                clause_id=clause.clause_id,
                source_span=token.span,
                evidence_ids=[f"SENSE-REFINEMENT:{lemma}"],
            )
            propositions.append(proposition)
            index = len(propositions) - 1
        updates = {
            "surface_predicate": token.surface,
            "sense_candidates": (positive or scored)[:4],
        }
        if selected is not None:
            second = positive[1].score if len(positive) > 1 else 0
            updates.update({
                "sense_id": selected.sense_id,
                "sense_label": selected.label,
                "sense_confidence": round(
                    min(1.0, selected.score / max(1, selected.score + second)),
                    4,
                ),
                "inference_sources": list(dict.fromkeys([
                    *proposition.inference_sources,
                    f"sense_refinement:{lemma}",
                ])),
            })
            fixed += 1
        elif proposition.intent_type in ACTION_INTENTS:
            updates.update({
                "sense_confidence": 0.0,
                "status": ItemStatus.AMBIGUOUS,
                "executable_candidate": False,
            })
        propositions[index] = proposition.model_copy(update=updates)
    return graph.model_copy(update={"propositions": propositions}), fixed


def _last_explicit_target(text: str, anchor: int) -> str | None:
    candidates: list[str] = []
    for match in _OBJECT_PATTERN.finditer(text[:anchor]):
        value = clean_fragment(match.group("value"))
        value = re.split(r"(?:してから|して|から|なら|そして|次に)", value)[-1]
        value = clean_fragment(value)
        if (
            value
            and _compact(value) not in _GENERIC_TARGETS
            and len(_compact(value)) >= 2
        ):
            candidates.append(value)
    return candidates[-1] if candidates else None


def _action_anchor(text: str, proposition: Proposition) -> int:
    anchor = proposition.source_span.start
    for surface in _ACTION_SURFACES.get(proposition.predicate, []):
        found = text.rfind(surface, 0, proposition.source_span.end)
        if found >= 0:
            anchor = max(anchor, found)
    return anchor


def _refine_ellipsis(
    graph: MeaningGraph,
    *,
    original_text: str,
) -> tuple[MeaningGraph, int]:
    propositions = list(graph.propositions)
    index = _entity_index(graph)
    fixed = 0
    for position, proposition in enumerate(propositions):
        if proposition.intent_type not in ACTION_INTENTS:
            continue
        targets = [
            item
            for item in proposition.arguments
            if item.role in {
                "object",
                "task",
                "action",
                "result",
                "scope",
                "reference",
                "destination",
            }
            and item.value
            and _compact(item.value) not in _GENERIC_TARGETS
        ]
        if any(not item.explicit for item in targets):
            continue
        if targets:
            continue
        target = _last_explicit_target(
            original_text,
            _action_anchor(original_text, proposition),
        )
        if not target:
            continue
        graph, entity_id = _ensure_entity(
            graph,
            index,
            target,
            entity_type="ellipsis_antecedent",
        )
        inferred = Argument(
            role="object",
            value=target,
            entity_id=entity_id,
            explicit=False,
            candidates=[target],
            status=ItemStatus.RESOLVED,
        )
        propositions[position] = proposition.model_copy(update={
            "arguments": [*proposition.arguments, inferred],
            "status": ItemStatus.RESOLVED,
            "executable_candidate": bool(
                not proposition.quoted
                and proposition.speech_act in {
                    "command",
                    "request",
                    "polite_request",
                }
            ),
            "inference_sources": list(dict.fromkeys([
                *proposition.inference_sources,
                "ellipsis_refinement:previous_explicit_object",
            ])),
        })
        fixed += 1
    return graph.model_copy(update={"propositions": propositions}), fixed


def _pragmatic_proposition(
    graph: MeaningGraph,
    *,
    original_text: str,
    marker: str,
    intent_type: str,
    speech_act: str,
    predicate: str,
    span: OriginalSpan,
    executable: bool,
    target: str | None = None,
) -> MeaningGraph:
    propositions = list(graph.propositions)
    overlapping = [
        index
        for index, item in enumerate(propositions)
        if item.source_span.start < span.end and span.start < item.source_span.end
    ]
    entity_index = _entity_index(graph)
    argument = None
    if target:
        graph, entity_id = _ensure_entity(
            graph,
            entity_index,
            target,
            entity_type="pragmatic_target",
        )
        argument = Argument(
            role="object",
            value=target,
            entity_id=entity_id,
            case_marker="を",
            explicit=True,
            status=ItemStatus.RESOLVED,
        )
    if overlapping:
        position = overlapping[-1]
        proposition = propositions[position]
        arguments = list(proposition.arguments)
        if argument and not any(item.value == target for item in arguments):
            arguments.append(argument)
        propositions[position] = proposition.model_copy(update={
            "intent_type": intent_type,
            "predicate": predicate,
            "speech_act": speech_act,
            "sentence_mood": (
                "interrogative" if speech_act == "polite_request" else "declarative"
            ),
            "arguments": arguments,
            "status": (
                ItemStatus.RESOLVED
                if not executable or target
                else ItemStatus.INSUFFICIENT
            ),
            "executable_candidate": bool(executable and target and not proposition.quoted),
            "pragmatic_markers": list(dict.fromkeys([
                *proposition.pragmatic_markers,
                marker,
            ])),
            "inference_sources": list(dict.fromkeys([
                *proposition.inference_sources,
                f"pragmatic_refinement:{marker}",
            ])),
        })
    else:
        clause = _clause(graph, span.start)
        propositions.append(Proposition(
            proposition_id=f"P-{len(propositions) + 1:03d}",
            predicate=predicate,
            intent_type=intent_type,
            value=span.source_text,
            arguments=[argument] if argument else [],
            speech_act=speech_act,
            sentence_mood=(
                "interrogative" if speech_act == "polite_request" else "declarative"
            ),
            executable_candidate=bool(executable and target),
            clause_id=clause.clause_id if clause else None,
            source_span=span,
            status=(
                ItemStatus.RESOLVED
                if not executable or target
                else ItemStatus.INSUFFICIENT
            ),
            evidence_ids=[f"PRAGMATIC-REFINEMENT:{marker}"],
            pragmatic_markers=[marker],
            inference_sources=[f"pragmatic_refinement:{marker}"],
        ))
    return graph.model_copy(update={"propositions": propositions})


def _refine_pragmatics(
    graph: MeaningGraph,
    *,
    original_text: str,
) -> tuple[MeaningGraph, int]:
    fixed = 0
    desire = re.search(
        r"(?P<target>[^、。！？!?]{1,40}?)(?:を)?直してほしい(?:です)?",
        original_text,
    )
    if desire:
        marker = "pragmatic.desire_request"
        if not any(marker in item.pragmatic_markers for item in graph.propositions):
            graph = _pragmatic_proposition(
                graph,
                original_text=original_text,
                marker=marker,
                intent_type="request",
                speech_act="request",
                predicate="変更する",
                span=OriginalSpan(
                    start=desire.start(),
                    end=desire.end(),
                    source_text=original_text[desire.start():desire.end()],
                ),
                executable=True,
                target=clean_fragment(desire.group("target")),
            )
            fixed += 1
        else:
            graph = _pragmatic_proposition(
                graph,
                original_text=original_text,
                marker=marker,
                intent_type="request",
                speech_act="request",
                predicate="変更する",
                span=OriginalSpan(
                    start=desire.start(),
                    end=desire.end(),
                    source_text=original_text[desire.start():desire.end()],
                ),
                executable=True,
                target=clean_fragment(desire.group("target")),
            )
            fixed += 1

    concern = re.search(r"このまま公開するのは不安です", original_text)
    if concern and not any(
        "pragmatic.concern" in item.pragmatic_markers
        for item in graph.propositions
    ):
        graph = _pragmatic_proposition(
            graph,
            original_text=original_text,
            marker="pragmatic.concern",
            intent_type="concern",
            speech_act="concern",
            predicate="懸念を表明する",
            span=OriginalSpan(
                start=concern.start(),
                end=concern.end(),
                source_text=concern.group(0),
            ),
            executable=False,
        )
        fixed += 1

    clarification = re.search(r"前提を合わせたい(?:です)?", original_text)
    if clarification and not any(
        "pragmatic.clarification_request" in item.pragmatic_markers
        for item in graph.propositions
    ):
        graph = _pragmatic_proposition(
            graph,
            original_text=original_text,
            marker="pragmatic.clarification_request",
            intent_type="clarification_request",
            speech_act="clarification_request",
            predicate="追加確認を求める",
            span=OriginalSpan(
                start=clarification.start(),
                end=clarification.end(),
                source_text=clarification.group(0),
            ),
            executable=False,
        )
        fixed += 1
    return graph, fixed


def _refine_sequence(
    graph: MeaningGraph,
    *,
    original_text: str,
) -> tuple[MeaningGraph, int]:
    if any(item.relation == "precedes" for item in graph.scope_edges):
        return graph, 0
    if not re.search(r"(?:前に|てから|その後|次に)", original_text):
        return graph, 0
    actions = sorted(
        (
            item
            for item in graph.propositions
            if item.intent_type in ACTION_INTENTS
        ),
        key=lambda item: (item.source_span.start, item.proposition_id),
    )
    if len(actions) < 2:
        return graph, 0
    edge = ScopeEdge(
        edge_id=f"R-{len(graph.scope_edges) + 1:03d}",
        source_id=actions[0].proposition_id,
        target_id=actions[-1].proposition_id,
        relation="precedes",
        marker="sequence_refinement",
        confidence=0.90,
        evidence_ids=["DISCOURSE:SEQUENCE_REFINEMENT"],
    )
    return graph.model_copy(update={
        "scope_edges": [*graph.scope_edges, edge],
    }), 1


def refine_graph(
    enricher: SemanticEnricher,
    graph: MeaningGraph,
    *,
    original_text: str,
    tokens,
) -> MeaningGraph:
    graph, sense_fixed = _refine_senses(
        enricher,
        graph,
        original_text=original_text,
        tokens=tokens,
    )
    graph, ellipsis_fixed = _refine_ellipsis(
        graph,
        original_text=original_text,
    )
    graph, pragmatic_fixed = _refine_pragmatics(
        graph,
        original_text=original_text,
    )
    graph, sequence_fixed = _refine_sequence(
        graph,
        original_text=original_text,
    )
    annotations = dict(graph.quality_annotations)
    annotations.update({
        "refined_senses": sense_fixed,
        "refined_ellipsis": ellipsis_fixed,
        "refined_pragmatics": pragmatic_fixed,
        "refined_sequence_edges": sequence_fixed,
    })
    graph = graph.model_copy(update={"quality_annotations": annotations})
    return graph.model_copy(update={"semantic_hash": _hash(graph)})


_INSTALLED = False


def install_semantic_refinement() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    original: Callable = SemanticEnricher.enrich

    def enrich(self, graph, **kwargs):
        enriched = original(self, graph, **kwargs)
        refined = refine_graph(
            self,
            enriched,
            original_text=kwargs["original_text"],
            tokens=kwargs["tokens"],
        )
        annotations = refined.quality_annotations
        self.last_metrics = {
            **self.last_metrics,
            "refined_sense_count": annotations.get("refined_senses", 0),
            "refined_ellipsis_count": annotations.get("refined_ellipsis", 0),
            "refined_pragmatic_count": annotations.get("refined_pragmatics", 0),
            "refined_sequence_edge_count": annotations.get(
                "refined_sequence_edges", 0
            ),
        }
        return refined

    SemanticEnricher.enrich = enrich
    _INSTALLED = True
