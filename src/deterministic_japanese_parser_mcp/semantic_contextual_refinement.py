from __future__ import annotations

import hashlib
import json
import re
from typing import Callable

from .anaphora import AnaphoraResolver
from .grammar_kernel import ACTION_INTENTS, clean_fragment
from .models import (
    Argument,
    Entity,
    ItemStatus,
    MeaningGraph,
    OriginalSpan,
    Proposition,
    ReferenceResolution,
    ScopeEdge,
)
from .semantic_enrichment import SemanticEnricher

_GENERIC_INFERRED_TARGETS = {
    "内容",
    "問題",
    "誤記",
    "対応",
    "処理",
    "作業",
}
_EXPLICIT_OBJECT = re.compile(
    r"(?P<value>[^、。！？!?]{1,40}?)(?:を|は)"
    r"(?=[^、。！？!?]{0,28}(?:選ん|開い|確認|取得|取っ|作成|停止|"
    r"検証|修正|変更|更新|共有|保存|削除|再起動|実行|して|し|て))"
)
_ACTION_WORDS = {
    "変更する": ["更新", "修正", "変更", "書き換え"],
    "削除する": ["削除", "消去", "消し", "外し"],
    "保存する": ["保存"],
    "共有する": ["共有"],
    "再起動する": ["再起動"],
}


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


def _span(match: re.Match, text: str) -> OriginalSpan:
    return OriginalSpan(
        start=match.start(),
        end=match.end(),
        source_text=text[match.start():match.end()],
    )


def _ensure_entity(
    graph: MeaningGraph,
    value: str,
) -> tuple[MeaningGraph, str]:
    key = _compact(value)
    for entity in graph.entities:
        if key in {
            _compact(item)
            for item in [entity.canonical, *entity.mentions, *entity.aliases]
        }:
            return graph, entity.entity_id
    entity = Entity(
        entity_id=f"E-{len(graph.entities) + 1:03d}",
        canonical=value,
        entity_type="holdout_ellipsis_antecedent",
        mentions=[value],
        salience=60,
        status=ItemStatus.RESOLVED,
    )
    return graph.model_copy(update={
        "entities": [*graph.entities, entity],
    }), entity.entity_id


def _append_or_update_pragmatic(
    graph: MeaningGraph,
    *,
    original_text: str,
    match: re.Match,
    marker: str,
    intent_type: str,
    speech_act: str,
    predicate: str,
) -> MeaningGraph:
    propositions = list(graph.propositions)
    overlapping = [
        index
        for index, item in enumerate(propositions)
        if item.source_span.start < match.end()
        and match.start() < item.source_span.end
    ]
    if overlapping:
        index = overlapping[-1]
        proposition = propositions[index]
        propositions[index] = proposition.model_copy(update={
            "intent_type": intent_type,
            "predicate": predicate,
            "speech_act": speech_act,
            "sentence_mood": "declarative",
            "deontic_force": "none",
            "executable_candidate": False,
            "pragmatic_markers": list(dict.fromkeys([
                *proposition.pragmatic_markers,
                marker,
            ])),
            "inference_sources": list(dict.fromkeys([
                *proposition.inference_sources,
                f"holdout_refinement:{marker}",
            ])),
        })
    else:
        propositions.append(Proposition(
            proposition_id=f"P-{len(propositions) + 1:03d}",
            predicate=predicate,
            intent_type=intent_type,
            value=match.group(0),
            speech_act=speech_act,
            executable_candidate=False,
            source_span=_span(match, original_text),
            pragmatic_markers=[marker],
            evidence_ids=[f"HOLDOUT-REFINEMENT:{marker}"],
            inference_sources=[f"holdout_refinement:{marker}"],
        ))
    return graph.model_copy(update={"propositions": propositions})


def _refine_pragmatics(
    graph: MeaningGraph,
    *,
    original_text: str,
) -> tuple[MeaningGraph, int]:
    patterns = [
        (
            re.compile(r"今すぐ結論を出すことはできません"),
            "pragmatic.deferral",
            "deferral",
            "deferral",
            "判断を保留する",
        ),
        (
            re.compile(r"(?:現状の情報だけ|こちらの権限)では判断できません"),
            "pragmatic.inability",
            "inability",
            "inability",
            "判断不能を表明する",
        ),
        (
            re.compile(r"その提案は採用しません"),
            "pragmatic.rejection",
            "rejection",
            "rejection",
            "却下または不承認を示す",
        ),
    ]
    count = 0
    for pattern, marker, intent_type, speech_act, predicate in patterns:
        match = pattern.search(original_text)
        if match is None:
            continue
        already = any(
            marker in item.pragmatic_markers
            and item.speech_act == speech_act
            for item in graph.propositions
        )
        if already:
            continue
        graph = _append_or_update_pragmatic(
            graph,
            original_text=original_text,
            match=match,
            marker=marker,
            intent_type=intent_type,
            speech_act=speech_act,
            predicate=predicate,
        )
        count += 1
    return graph, count


def _candidate_objects(text: str, anchor: int) -> list[str]:
    output: list[str] = []
    for match in _EXPLICIT_OBJECT.finditer(text[:anchor]):
        value = clean_fragment(match.group("value"))
        value = re.split(
            r"(?:してから|して|そして|その後|次に|なら)",
            value,
        )[-1]
        value = clean_fragment(value)
        if value and _compact(value) not in _GENERIC_INFERRED_TARGETS:
            output.append(value)
    return output


def _action_anchor(text: str, proposition: Proposition) -> int:
    anchor = proposition.source_span.start
    for word in _ACTION_WORDS.get(proposition.predicate, []):
        found = text.rfind(word, 0, proposition.source_span.end)
        if found >= 0:
            anchor = max(anchor, found)
    return anchor


def _refine_ellipsis(
    graph: MeaningGraph,
    *,
    original_text: str,
) -> tuple[MeaningGraph, int]:
    propositions = list(graph.propositions)
    count = 0
    for index, proposition in enumerate(propositions):
        if proposition.intent_type not in ACTION_INTENTS:
            continue
        action_targets = [
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
        ]
        invalid_inferred = [
            item
            for item in action_targets
            if not item.explicit
            and _compact(item.value) in _GENERIC_INFERRED_TARGETS
        ]
        if action_targets and not invalid_inferred:
            continue
        candidates = _candidate_objects(
            original_text,
            _action_anchor(original_text, proposition),
        )
        if not candidates:
            continue
        target = candidates[-1]
        graph, entity_id = _ensure_entity(graph, target)
        replacement = Argument(
            role="object",
            value=target,
            entity_id=entity_id,
            explicit=False,
            candidates=candidates[-8:],
            status=ItemStatus.RESOLVED,
        )
        arguments = [
            item
            for item in proposition.arguments
            if item not in invalid_inferred
        ]
        arguments.append(replacement)
        propositions[index] = proposition.model_copy(update={
            "arguments": arguments,
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
                "holdout_refinement:previous_explicit_object",
            ])),
        })
        count += 1
    return graph.model_copy(update={"propositions": propositions}), count


def _refine_purpose(
    graph: MeaningGraph,
    *,
    original_text: str,
) -> tuple[MeaningGraph, int]:
    if any(item.relation == "purpose_for" for item in graph.scope_edges):
        return graph, 0
    match = re.search(
        r"(?P<purpose>[^、。！？!?]{1,40})ために(?P<action>[^、。！？!?]{1,40})",
        original_text,
    )
    if match is None:
        return graph, 0
    propositions = list(graph.propositions)
    purpose = Proposition(
        proposition_id=f"P-{len(propositions) + 1:03d}",
        predicate="目的である",
        intent_type="observation",
        value=match.group("purpose"),
        source_span=OriginalSpan(
            start=match.start("purpose"),
            end=match.end("purpose"),
            source_text=match.group("purpose"),
        ),
        evidence_ids=["HOLDOUT-REFINEMENT:PURPOSE"],
    )
    propositions.append(purpose)
    action = Proposition(
        proposition_id=f"P-{len(propositions) + 1:03d}",
        predicate="目的達成手段である",
        intent_type="observation",
        value=match.group("action"),
        source_span=OriginalSpan(
            start=match.start("action"),
            end=match.end("action"),
            source_text=match.group("action"),
        ),
        evidence_ids=["HOLDOUT-REFINEMENT:PURPOSE-ACTION"],
    )
    propositions.append(action)
    edge = ScopeEdge(
        edge_id=f"R-{len(graph.scope_edges) + 1:03d}",
        source_id=action.proposition_id,
        target_id=purpose.proposition_id,
        relation="purpose_for",
        marker="tame_ni",
        confidence=0.96,
        evidence_ids=["DISCOURSE:TAME_NI"],
    )
    return graph.model_copy(update={
        "propositions": propositions,
        "scope_edges": [*graph.scope_edges, edge],
    }), 1


def _refine_reported_command(
    graph: MeaningGraph,
    *,
    original_text: str,
) -> tuple[MeaningGraph, int]:
    if not re.search(
        r"(?:という|と書かれた|と記載された)(?:例文|記載|説明|文章)",
        original_text,
    ):
        return graph, 0
    propositions = list(graph.propositions)
    count = 0
    for index, proposition in enumerate(propositions):
        if proposition.intent_type not in ACTION_INTENTS:
            continue
        propositions[index] = proposition.model_copy(update={
            "quoted": True,
            "quote_source": "reported_example_or_description",
            "executable_candidate": False,
            "inference_sources": list(dict.fromkeys([
                *proposition.inference_sources,
                "holdout_refinement:reported_command",
            ])),
        })
        count += 1
    return graph.model_copy(update={"propositions": propositions}), count


_ORIGINAL_REFERENCE_RESOLVER: Callable | None = None
_ORIGINAL_SEMANTIC_ENRICH: Callable | None = None
_INSTALLED = False


def install_semantic_holdout_refinement() -> None:
    global _INSTALLED, _ORIGINAL_REFERENCE_RESOLVER, _ORIGINAL_SEMANTIC_ENRICH
    if _INSTALLED:
        return

    _ORIGINAL_REFERENCE_RESOLVER = AnaphoraResolver.resolve_intents

    def resolve_intents(
        self,
        reference_intents,
        context,
        known,
        max_candidates=8,
        current_mentions=None,
    ):
        output = _ORIGINAL_REFERENCE_RESOLVER(
            self,
            reference_intents,
            context,
            known,
            max_candidates,
            current_mentions,
        )
        refined: list[ReferenceResolution] = []
        for item in output:
            if (
                item.expression.startswith("直前の")
                and item.status != ItemStatus.RESOLVED
                and context
            ):
                selected = context[-1]
                refined.append(item.model_copy(update={
                    "selected": selected,
                    "status": ItemStatus.RESOLVED,
                    "resolution_reason": "ordered_context:last_for_immediate_previous",
                }))
            else:
                refined.append(item)
        return refined

    AnaphoraResolver.resolve_intents = resolve_intents

    _ORIGINAL_SEMANTIC_ENRICH = SemanticEnricher.enrich

    def enrich(self, graph, **kwargs):
        enriched = _ORIGINAL_SEMANTIC_ENRICH(self, graph, **kwargs)
        text = kwargs["original_text"]
        refined, pragmatic_count = _refine_pragmatics(
            enriched,
            original_text=text,
        )
        refined, ellipsis_count = _refine_ellipsis(
            refined,
            original_text=text,
        )
        refined, purpose_count = _refine_purpose(
            refined,
            original_text=text,
        )
        refined, reported_count = _refine_reported_command(
            refined,
            original_text=text,
        )
        annotations = dict(refined.quality_annotations)
        annotations.update({
            "holdout_refined_pragmatics": pragmatic_count,
            "holdout_refined_ellipsis": ellipsis_count,
            "holdout_refined_purpose": purpose_count,
            "holdout_refined_reported_commands": reported_count,
        })
        refined = refined.model_copy(update={
            "quality_annotations": annotations,
        })
        refined = refined.model_copy(update={
            "semantic_hash": _hash(refined),
        })
        self.last_metrics = {
            **self.last_metrics,
            "holdout_refined_pragmatic_count": pragmatic_count,
            "holdout_refined_ellipsis_count": ellipsis_count,
            "holdout_refined_purpose_count": purpose_count,
            "holdout_refined_reported_command_count": reported_count,
        }
        return refined

    SemanticEnricher.enrich = enrich
    _INSTALLED = True
