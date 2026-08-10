from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from unified_semantic_data.canonical_dictionary import compile_canonical_dictionary  # noqa: E402
from unified_semantic_data.canonical_runtime_projection import (  # noqa: E402
    compile_runtime_projection,
    project_record,
)


def _source(dataset: str, record_id: str) -> dict:
    return {
        "dataset": dataset,
        "version": "1.0",
        "license": "MIT",
        "source_id": record_id,
        "source_url": f"https://example.invalid/{dataset}",
        "source_sha256": hashlib.sha256(dataset.encode()).hexdigest(),
        "attribution": dataset,
    }


def _record(record_id: str, dataset: str, gloss: str) -> dict:
    return {
        "record_id": record_id,
        "input_sha256": hashlib.sha256(record_id.encode()).hexdigest(),
        "lemma": "走る",
        "surfaces": ["走る"],
        "normalized_surfaces": ["走る"],
        "readings": ["はしる"],
        "part_of_speech": ["動詞"],
        "morphology": {
            "backend": "fixture",
            "forms": [],
            "conjugation": {"type": "五段"},
        },
        "domains": ["general"],
        "usage_labels": [],
        "feature_type": "",
        "meaning_candidates": [
            {
                "candidate_id": f"{record_id}:sense:001",
                "label": gloss,
                "glosses": [gloss],
                "part_of_speech": ["動詞"],
                "domains": ["general"],
                "parameters": {},
                "register": {},
                "context": {},
                "review_status": "approved",
            }
        ],
        "polarity": "neutral",
        "intensity": 0.0,
        "semantic_targets": ["lexicon"],
        "parameters": {},
        "register": {},
        "context_conditions": {
            "required_any": [],
            "required_all": [],
            "forbidden_any": [],
            "required_social": [],
            "required_discourse": [],
        },
        "task_candidates": [],
        "examples": {"positive": [], "negative": [], "boundary": []},
        "risk_class": "semantic",
        "external_action_risk": False,
        "source": _source(dataset, record_id),
        "approval": {
            "scopes": {
                "lexical": "approved",
                "semantic": "approved",
                "pragmatic": "approved",
                "task": "approved",
                "external_action": "approved",
            },
            "approved_scopes": [
                "external_action",
                "lexical",
                "pragmatic",
                "semantic",
                "task",
            ],
            "review_scopes": [],
            "blockers_by_scope": {
                "lexical": [],
                "semantic": [],
                "pragmatic": [],
                "task": [],
                "external_action": [],
            },
        },
        "runtime_eligible": True,
    }


def _review_root(path: Path) -> Path:
    path.mkdir()
    records = [
        _record("JMD-001", "jmdict", "足を交互に動かして速く移動する"),
        _record("WN-001", "wordnet-ja", "一定の方向へ素早く移動する"),
    ]
    (path / "approved-records.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records),
        encoding="utf-8",
    )
    (path / "manifest.json").write_text(
        json.dumps({"fixture": True}) + "\n",
        encoding="utf-8",
    )
    return path


def test_runtime_projection_uses_canonical_dictionary_as_sole_record_source(
    tmp_path: Path,
) -> None:
    review = _review_root(tmp_path / "review")
    dictionary_root = tmp_path / "dictionary"
    runtime_root = tmp_path / "runtime"
    dictionary_manifest = compile_canonical_dictionary(
        review, dictionary_root, shard_size=100
    )
    runtime_manifest = compile_runtime_projection(
        dictionary_root, runtime_root, shard_size=100
    )

    assert dictionary_manifest["record_count"] == 1
    assert runtime_manifest["record_count"] == 1
    assert runtime_manifest["runtime_record_count"] == 1
    assert runtime_manifest["approved_only"] is True
    assert runtime_manifest["automatic_external_action"] is False
    assert runtime_manifest["boundaries"]["source_is_mcp_canonical_dictionary"] is True
    assert runtime_manifest["boundaries"]["meaning_re_resolution"] is False

    with gzip.open(
        runtime_root / "records/records-0000.jsonl.gz",
        "rt",
        encoding="utf-8",
    ) as handle:
        row = json.loads(next(handle))
    assert row["source_kind"] == "canonical_dictionary"
    assert row["source"]["dataset"] == "MCP Canonical Dictionary"
    assert row["record_id"].startswith("CDICT-")
    assert len(row["meaning_candidates"]) == 2
    assert {item["review_status"] for item in row["meaning_candidates"]} == {
        "approved"
    }
    assert all(item["evidence_ids"] for item in row["meaning_candidates"])


def test_project_record_preserves_action_risk_conservatively() -> None:
    record = {
        "dictionary_id": "CDICT-test",
        "lemma": "実行",
        "surfaces": ["実行"],
        "normalized_surfaces": ["実行"],
        "readings": ["じっこう"],
        "part_of_speech": ["名詞"],
        "morphology": {},
        "domains": [],
        "senses": [
            {
                "sense_id": "CDICT-test:S-1",
                "labels": ["実際に行うこと"],
                "glosses": ["実際に行うこと"],
                "part_of_speech": ["名詞"],
                "domains": [],
                "parameters": {},
                "register": {},
                "context": {},
                "source_evidence": [{"source_record_id": "SRC-1"}],
            }
        ],
        "pragmatics": {},
        "semantic_facets": {
            "risk_classes": ["semantic", "action"],
            "semantic_targets": ["lexicon"],
            "usage_labels": [],
            "feature_types": [],
        },
    }
    projected = project_record(record)
    assert projected["risk_class"] == "action"
    assert projected["external_action_risk"] is False
