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
from unified_semantic_data.canonical_meaning_provenance import (  # noqa: E402
    compile_meaning_provenance_view,
)


def _record() -> dict:
    return {
        "record_id": "TARGET-1",
        "input_sha256": hashlib.sha256(b"target").hexdigest(),
        "lemma": "めんこい",
        "surfaces": ["めんこい"],
        "normalized_surfaces": ["めんこい"],
        "readings": ["めんこい"],
        "part_of_speech": ["形容詞"],
        "morphology": {"backend": "fixture", "forms": [], "conjugation": {}},
        "domains": ["dialect"],
        "usage_labels": [],
        "feature_type": "",
        "meaning_candidates": [{
            "candidate_id": "TARGET-1:semantic-enrichment:001",
            "label": "かわいい、愛らしい",
            "glosses": ["かわいい、愛らしい"],
            "part_of_speech": ["形容詞"],
            "domains": ["dialect"],
            "parameters": {},
            "register": {},
            "context": {},
            "evidence_ids": ["reference:REF-1"],
            "review_status": "approved",
        }],
        "polarity": "positive",
        "intensity": 0.5,
        "semantic_targets": ["lexicon"],
        "parameters": {},
        "register": {},
        "context_conditions": {},
        "task_candidates": [],
        "examples": {"positive": [], "negative": [], "boundary": []},
        "risk_class": "semantic",
        "external_action_risk": False,
        "source": {
            "dataset": "target-candidate-source",
            "version": "1",
            "license": "MIT",
            "source_id": "TARGET-1",
            "source_url": "https://example.invalid/target",
            "source_sha256": hashlib.sha256(b"target-source").hexdigest(),
            "attribution": "target",
        },
        "approval": {
            "scopes": {
                "lexical": "approved", "semantic": "approved",
                "pragmatic": "approved", "task": "approved",
                "external_action": "approved",
            },
            "approved_scopes": [
                "external_action", "lexical", "pragmatic", "semantic", "task"
            ],
            "review_scopes": [],
            "blockers_by_scope": {
                "lexical": [], "semantic": [], "pragmatic": [],
                "task": [], "external_action": [],
            },
        },
        "runtime_eligible": True,
    }


def _review_root(path: Path) -> Path:
    path.mkdir()
    (path / "approved-records.jsonl").write_text(
        json.dumps(_record(), ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (path / "manifest.json").write_text("{}\n", encoding="utf-8")
    queue = {
        "record_id": "TARGET-1",
        "proposed_meaning_candidates": [{
            "candidate_id": "TARGET-1:semantic-enrichment:001",
            "glosses": ["かわいい、愛らしい"],
            "evidence_ids": ["reference:REF-1"],
        }],
        "evidence": [{
            "reference_record_id": "reference:REF-1",
            "score": 12,
            "source": {
                "dataset": "reference-dictionary",
                "version": "2026-08",
                "license": "CC BY 4.0",
                "source_id": "REF-1",
                "source_url": "https://example.invalid/reference",
                "source_sha256": hashlib.sha256(b"reference").hexdigest(),
                "attribution": "reference author",
            },
        }],
    }
    (path / "semantic-enrichment-queue.jsonl").write_text(
        json.dumps(queue, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path


def test_canonical_sense_points_to_definition_reference_not_target_record(tmp_path: Path) -> None:
    review = _review_root(tmp_path / "review")
    master = tmp_path / "master"
    refined = tmp_path / "refined"
    compile_canonical_dictionary(review, master, shard_size=100)
    manifest = compile_meaning_provenance_view(
        review, master, refined, shard_size=100
    )
    assert manifest["sense_source_replacement_count"] == 1
    with gzip.open(
        refined / "records/dictionary-0000.jsonl.gz", "rt", encoding="utf-8"
    ) as handle:
        record = json.loads(next(handle))
    sense = record["senses"][0]
    assert sense["glosses"] == ["かわいい、愛らしい"]
    assert sense["meaning_provenance_mode"] == "semantic-enrichment-reference"
    assert sense["derivation_target_record_ids"] == ["TARGET-1"]
    assert sense["source_evidence"][0]["dataset"] == "reference-dictionary"
    assert sense["source_evidence"][0]["source_id"] == "REF-1"
    assert sense["source_evidence"][0]["derivation_target_record_id"] == "TARGET-1"
    assert sense["source_evidence"][0]["source_sha256"] == hashlib.sha256(
        b"reference"
    ).hexdigest()


def test_source_authored_sense_keeps_original_source_when_no_enrichment_match(tmp_path: Path) -> None:
    review = tmp_path / "review"
    review.mkdir()
    row = _record()
    row["meaning_candidates"][0]["candidate_id"] = "TARGET-1:source-sense"
    row["meaning_candidates"][0]["glosses"] = ["元Source自身の意味"]
    row["meaning_candidates"][0]["label"] = "元Source自身の意味"
    (review / "approved-records.jsonl").write_text(
        json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (review / "manifest.json").write_text("{}\n", encoding="utf-8")
    master = tmp_path / "master"
    refined = tmp_path / "refined"
    compile_canonical_dictionary(review, master, shard_size=100)
    manifest = compile_meaning_provenance_view(
        review, master, refined, shard_size=100
    )
    assert manifest["sense_source_replacement_count"] == 0
    with gzip.open(
        refined / "records/dictionary-0000.jsonl.gz", "rt", encoding="utf-8"
    ) as handle:
        record = json.loads(next(handle))
    sense = record["senses"][0]
    assert sense["meaning_provenance_mode"] == "source-authored-record"
    assert sense["source_evidence"][0]["dataset"] == "target-candidate-source"
