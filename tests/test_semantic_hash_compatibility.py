from __future__ import annotations

import hashlib
import json

from deterministic_japanese_parser_mcp.models import MeaningGraph


# MeaningGraph.semantic_hash currently hashes every graph field except
# semantic_hash itself. This registry is therefore a compatibility gate:
# extending MeaningGraph without an explicit graph/hash-version decision must
# fail CI instead of silently changing every existing semantic hash.
_HASHED_FIELDS_BY_GRAPH_VERSION = {
    "2.3.0": (
        "graph_version",
        "entities",
        "clauses",
        "propositions",
        "lexical_nodes",
        "scope_edges",
        "reading_analysis",
        "language_features",
        "unresolved",
        "decision_state_changes",
        "evidence_rule_ids",
        "context_version",
        "quality_annotations",
    ),
}

# There are two existing byte encodings in the current runtime. Both are
# intentionally frozen here before Router / Recovery / field-level evidence
# adds any new MeaningGraph state.
_EMPTY_GRAPH_ORDERED_HASH = (
    "b1a09cf413274716a36d8cbdec749b0b696ed2cb4212be5d5f980926d7041760"
)
_EMPTY_GRAPH_CANONICAL_HASH = (
    "65855b076b5650437fb8fff1b18ec6114a5f3598ff7f53c602c4e9ddc87a885d"
)


def _hashed_field_names() -> tuple[str, ...]:
    return tuple(
        name for name in MeaningGraph.model_fields if name != "semantic_hash"
    )


def _ordered_hash(graph: MeaningGraph) -> str:
    return hashlib.sha256(
        graph.model_dump_json(exclude={"semantic_hash"}).encode("utf-8")
    ).hexdigest()


def _canonical_hash(graph: MeaningGraph) -> str:
    payload = graph.model_dump(exclude={"semantic_hash"}, mode="json")
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def test_meaning_graph_schema_has_registered_hash_contract():
    graph = MeaningGraph()

    assert graph.graph_version in _HASHED_FIELDS_BY_GRAPH_VERSION
    assert _hashed_field_names() == _HASHED_FIELDS_BY_GRAPH_VERSION[
        graph.graph_version
    ]


def test_empty_meaning_graph_ordered_hash_is_backward_compatible():
    assert _ordered_hash(MeaningGraph()) == _EMPTY_GRAPH_ORDERED_HASH


def test_empty_meaning_graph_canonical_hash_is_backward_compatible():
    assert _canonical_hash(MeaningGraph()) == _EMPTY_GRAPH_CANONICAL_HASH


def test_semantic_hash_field_is_not_self_hashed():
    first = MeaningGraph(semantic_hash="old")
    second = MeaningGraph(semantic_hash="new")

    assert _ordered_hash(first) == _ordered_hash(second)
    assert _canonical_hash(first) == _canonical_hash(second)
