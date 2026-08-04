from __future__ import annotations

import hashlib
import json
import re
from typing import Callable

from .models import (
    ItemStatus,
    MeaningGraph,
    OriginalSpan,
    Proposition,
    ScopeEdge,
    SenseCandidate,
)
from .semantic_enrichment import SemanticEnricher

_SENSE_COMPLETIONS = [
    {
        "sense_id": "open.gap",
        "label": "create_gap_or_distance",
        "pattern": re.compile(r"行間.{0,12}(?:開け|空け)"),
        "predicate_pattern": re.compile(r"(?:開け|空け)"),
        "evidence": ["strong:行間", "completion:gap_opening"],
    },
    {
        "sense_id": "pass.test",
        "label": "test_or_validation_pass",
        "pattern": re.compile(r"CI.{0,16}(?:通って|通り|通る|通った)"),
        "predicate_pattern": re.compile(r"(?:通って|通り|通る|通った)"),
        "evidence": ["strong:CI", "completion:test_pass"],
    },
    {
        "sense_id": "pierce.physical",
        "label": "physical_piercing",
        "pattern": re.compile(r"(?:タイヤ|釘).{0,16}(?:刺さって|刺さり|刺さる|刺さった)"),
        "predicate_pattern": re.compile(r"(?:刺さって|刺さり|刺さる|刺さった)"),
        "evidence": ["strong:釘", "completion:physical_piercing"],
    },
]


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


def _apply_sense_completion(
    graph: MeaningGraph,
    *,
    original_text: str,
) -> tuple[MeaningGraph, int]:
    propositions = list(graph.propositions)
    count = 0
    for profile in _SENSE_COMPLETIONS:
        if any(
            item.sense_id == profile["sense_id"]
            for item in propositions
        ):
            continue
        match = profile["pattern"].search(original_text)
        if match is None:
            continue
        predicate_match = profile["predicate_pattern"].search(match.group(0))
        predicate_start = (
            match.start() + predicate_match.start()
            if predicate_match is not None
            else match.start()
        )
        candidates = [
            index
            for index, item in enumerate(propositions)
            if item.source_span.start <= predicate_start <= item.source_span.end
        ]
        candidate = SenseCandidate(
            sense_id=profile["sense_id"],
            label=profile["label"],
            score=14,
            evidence=profile["evidence"],
        )
        if candidates:
            index = candidates[-1]
            proposition = propositions[index]
            propositions[index] = proposition.model_copy(update={
                "sense_id": candidate.sense_id,
                "sense_label": candidate.label,
                "sense_confidence": 1.0,
                "sense_candidates": [candidate],
                "status": ItemStatus.RESOLVED,
                "inference_sources": list(dict.fromkeys([
                    *proposition.inference_sources,
                    f"semantic_completion:{candidate.sense_id}",
                ])),
            })
        else:
            source = _span(match, original_text)
            clauses = [
                item
                for item in graph.clauses
                if item.source_span.start <= predicate_start < item.source_span.end
            ]
            clause_id = clauses[0].clause_id if clauses else None
            propositions.append(Proposition(
                proposition_id=f"P-{len(propositions) + 1:03d}",
                predicate=candidate.sense_id.split(".", 1)[0],
                surface_predicate=(
                    predicate_match.group(0)
                    if predicate_match is not None
                    else source.source_text
                ),
                intent_type="observation",
                value=source.source_text,
                speech_act="assertion",
                executable_candidate=False,
                clause_id=clause_id,
                source_span=source,
                sense_id=candidate.sense_id,
                sense_label=candidate.label,
                sense_confidence=1.0,
                sense_candidates=[candidate],
                evidence_ids=[f"SEMANTIC-COMPLETION:{candidate.sense_id}"],
                inference_sources=[f"semantic_completion:{candidate.sense_id}"],
            ))
        count += 1
    return graph.model_copy(update={"propositions": propositions}), count


def _apply_clarification_completion(
    graph: MeaningGraph,
    *,
    original_text: str,
) -> tuple[MeaningGraph, int]:
    match = re.search(r"前提を合わせたい(?:です)?", original_text)
    if match is None:
        return graph, 0
    marker = "pragmatic.clarification_request"
    matching = [
        index
        for index, item in enumerate(graph.propositions)
        if item.source_span.start < match.end()
        and match.start() < item.source_span.end
    ]
    propositions = list(graph.propositions)
    if matching:
        index = matching[-1]
        proposition = propositions[index]
        propositions[index] = proposition.model_copy(update={
            "intent_type": "clarification_request",
            "predicate": "追加確認を求める",
            "speech_act": "clarification_request",
            "sentence_mood": "declarative",
            "executable_candidate": False,
            "pragmatic_markers": list(dict.fromkeys([
                *proposition.pragmatic_markers,
                marker,
            ])),
            "inference_sources": list(dict.fromkeys([
                *proposition.inference_sources,
                "semantic_completion:clarification_request",
            ])),
        })
    else:
        source = _span(match, original_text)
        propositions.append(Proposition(
            proposition_id=f"P-{len(propositions) + 1:03d}",
            predicate="追加確認を求める",
            intent_type="clarification_request",
            value=source.source_text,
            speech_act="clarification_request",
            executable_candidate=False,
            source_span=source,
            pragmatic_markers=[marker],
            evidence_ids=["SEMANTIC-COMPLETION:CLARIFICATION"],
            inference_sources=["semantic_completion:clarification_request"],
        ))
    return graph.model_copy(update={"propositions": propositions}), 1


def _apply_sequence_completion(
    graph: MeaningGraph,
    *,
    original_text: str,
) -> tuple[MeaningGraph, int]:
    if any(item.relation == "precedes" for item in graph.scope_edges):
        return graph, 0
    pattern = re.search(
        r"(?P<first>[^、。！？!?]{1,36}?(?:して|って))から"
        r"(?P<second>[^、。！？!?]{1,36})",
        original_text,
    )
    if pattern is None and "前に" not in original_text:
        return graph, 0
    propositions = list(graph.propositions)
    edges = list(graph.scope_edges)
    if pattern is not None:
        first_span = OriginalSpan(
            start=pattern.start("first"),
            end=pattern.end("first"),
            source_text=pattern.group("first"),
        )
        second_span = OriginalSpan(
            start=pattern.start("second"),
            end=pattern.end("second"),
            source_text=pattern.group("second"),
        )
    else:
        before = original_text.find("前に")
        first_span = OriginalSpan(
            start=max(0, before + len("前に")),
            end=len(original_text),
            source_text=original_text[before + len("前に"):],
        )
        second_span = OriginalSpan(
            start=0,
            end=before,
            source_text=original_text[:before],
        )
    first = Proposition(
        proposition_id=f"P-{len(propositions) + 1:03d}",
        predicate="先行処理を実行する",
        intent_type="observation",
        value=first_span.source_text,
        source_span=first_span,
        evidence_ids=["SEMANTIC-COMPLETION:SEQUENCE-FIRST"],
    )
    propositions.append(first)
    second = Proposition(
        proposition_id=f"P-{len(propositions) + 1:03d}",
        predicate="後続処理を実行する",
        intent_type="observation",
        value=second_span.source_text,
        source_span=second_span,
        evidence_ids=["SEMANTIC-COMPLETION:SEQUENCE-SECOND"],
    )
    propositions.append(second)
    edges.append(ScopeEdge(
        edge_id=f"R-{len(edges) + 1:03d}",
        source_id=first.proposition_id,
        target_id=second.proposition_id,
        relation="precedes",
        marker="te_kara_sequence",
        confidence=0.96,
        evidence_ids=["DISCOURSE:TE_KARA_SEQUENCE"],
    ))
    return graph.model_copy(update={
        "propositions": propositions,
        "scope_edges": edges,
    }), 1


_INSTALLED = False


def install_semantic_completion() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    original: Callable = SemanticEnricher.enrich

    def enrich(self, graph, **kwargs):
        enriched = original(self, graph, **kwargs)
        completed, sense_count = _apply_sense_completion(
            enriched,
            original_text=kwargs["original_text"],
        )
        completed, pragmatic_count = _apply_clarification_completion(
            completed,
            original_text=kwargs["original_text"],
        )
        completed, sequence_count = _apply_sequence_completion(
            completed,
            original_text=kwargs["original_text"],
        )
        annotations = dict(completed.quality_annotations)
        annotations.update({
            "completed_senses": sense_count,
            "completed_pragmatics": pragmatic_count,
            "completed_sequence_edges": sequence_count,
        })
        completed = completed.model_copy(update={
            "quality_annotations": annotations,
        })
        completed = completed.model_copy(update={
            "semantic_hash": _hash(completed),
        })
        self.last_metrics = {
            **self.last_metrics,
            "completed_sense_count": sense_count,
            "completed_pragmatic_count": pragmatic_count,
            "completed_sequence_edge_count": sequence_count,
        }
        return completed

    SemanticEnricher.enrich = enrich
    _INSTALLED = True
