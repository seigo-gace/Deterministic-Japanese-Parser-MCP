from __future__ import annotations

import gzip
import json
from pathlib import Path

from deterministic_japanese_parser_mcp.models import (
    ItemStatus,
    MeaningGraph,
    OriginalSpan,
    Proposition,
    Token,
)
from deterministic_japanese_parser_mcp.semantic_data_runtime import SemanticDataRuntime


def _write_json_gzip(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True)


def _runtime_with_ambiguous_particle(tmp_path: Path) -> SemanticDataRuntime:
    root = tmp_path / "compiled"
    indexes = root / "indexes"
    records = root / "records"
    indexes.mkdir(parents=True)
    records.mkdir(parents=True)

    record_id = "SEM-PARTICLE-HA-001"
    record = {
        "record_id": record_id,
        "lemma": "は",
        "surfaces": ["は"],
        "readings": ["ハ"],
        "part_of_speech": ["助詞"],
        "risk_class": "semantic",
        "semantic_targets": ["lexicon"],
        "meaning_candidates": [
            {
                "candidate_id": f"{record_id}:topic",
                "label": "topic",
                "review_status": "approved",
            },
            {
                "candidate_id": f"{record_id}:contrast",
                "label": "contrast",
                "review_status": "approved",
            },
        ],
        "approval": {
            "approved_scopes": ["semantic"],
            "blockers_by_scope": {},
        },
    }
    with gzip.open(
        records / "records-0000.jsonl.gz", "wt", encoding="utf-8"
    ) as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    manifest = {
        "approved_only": True,
        "automatic_external_action": False,
        "preserve_ambiguity": True,
        "record_count": 1,
        "runtime_record_count": 1,
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    _write_json_gzip(indexes / "runtime-surface-index.json.gz", {"は": [record_id]})
    _write_json_gzip(indexes / "runtime-reading-index.json.gz", {"ハ": [record_id]})
    _write_json_gzip(
        indexes / "runtime-record-locator.json.gz",
        {record_id: {"shard": 0, "line": 1}},
    )
    # The constructor validates the legacy/full indexes before selecting the
    # runtime-only indexes, so keep the complete set present as well.
    _write_json_gzip(indexes / "surface-index.json.gz", {"は": [record_id]})
    _write_json_gzip(indexes / "reading-index.json.gz", {"ハ": [record_id]})
    _write_json_gzip(
        indexes / "record-locator.json.gz",
        {record_id: {"shard": 0, "line": 1}},
    )
    return SemanticDataRuntime(root)


def test_generic_particle_ambiguity_does_not_downgrade_preserve_constraint(
    tmp_path: Path,
) -> None:
    runtime = _runtime_with_ambiguous_particle(tmp_path)
    text = "UIは維持する"
    source_span = OriginalSpan(start=0, end=len(text), source_text=text)
    graph = MeaningGraph(
        propositions=[
            Proposition(
                proposition_id="P-001",
                predicate="維持する",
                intent_type="preserve",
                value="UI",
                source_span=source_span,
                status=ItemStatus.RESOLVED,
            )
        ]
    )
    token = Token(
        surface="は",
        normalized="は",
        reading="ハ",
        pos=["助詞", "係助詞"],
        span=OriginalSpan(start=2, end=3, source_text="は"),
    )

    enriched = runtime.enrich(
        graph,
        tokens=[token],
        original_text=text,
        conversation_context=[],
        known_entities=[],
    )

    proposition = enriched.propositions[0]
    assert proposition.intent_type == "preserve"
    assert proposition.status == ItemStatus.RESOLVED
    assert proposition.sense_id is None
    assert proposition.sense_candidates == []
    assert enriched.unresolved == []
