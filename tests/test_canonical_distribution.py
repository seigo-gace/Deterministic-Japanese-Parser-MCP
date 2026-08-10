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
from unified_semantic_data.canonical_distribution import (  # noqa: E402
    compile_public_dictionary_view,
)
from unified_semantic_data.license_policy import classify_data_license  # noqa: E402


def _record(record_id: str, dataset: str, license_value: str, gloss: str) -> dict:
    return {
        "record_id": record_id,
        "input_sha256": hashlib.sha256(record_id.encode()).hexdigest(),
        "lemma": "分類",
        "surfaces": ["分類"],
        "normalized_surfaces": ["分類"],
        "readings": ["ぶんるい"],
        "part_of_speech": ["名詞"],
        "morphology": {"backend": "fixture", "forms": [], "conjugation": {}},
        "domains": ["general"],
        "usage_labels": [],
        "feature_type": "",
        "meaning_candidates": [
            {
                "candidate_id": f"{record_id}:sense:001",
                "label": gloss,
                "glosses": [gloss],
                "part_of_speech": ["名詞"],
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
        "context_conditions": {},
        "task_candidates": [],
        "examples": {"positive": [], "negative": [], "boundary": []},
        "risk_class": "semantic",
        "external_action_risk": False,
        "source": {
            "dataset": dataset,
            "version": "1",
            "license": license_value,
            "source_id": record_id,
            "source_url": "https://example.invalid",
            "source_sha256": hashlib.sha256(dataset.encode()).hexdigest(),
            "attribution": dataset,
        },
        "approval": {
            "scopes": {
                "lexical": "approved",
                "semantic": "approved",
                "pragmatic": "approved",
                "task": "approved",
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


def _review_root(path: Path, records: list[dict]) -> Path:
    path.mkdir()
    (path / "approved-records.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records),
        encoding="utf-8",
    )
    (path / "manifest.json").write_text("{}\n", encoding="utf-8")
    return path


def test_license_classifier_blocks_nc_and_nd_but_preserves_sharealike() -> None:
    assert classify_data_license("CC BY-NC-SA 3.0")["public_dictionary_allowed"] is False
    assert classify_data_license("CC BY-ND 4.0")["public_dictionary_allowed"] is False
    sharealike = classify_data_license("CC BY-SA 4.0")
    assert sharealike["public_dictionary_allowed"] is True
    assert sharealike["tier"] == "sharealike"
    assert classify_data_license("MIT")["tier"] == "permissive"


def test_public_view_keeps_permissive_sense_and_excludes_noncommercial_sense(
    tmp_path: Path,
) -> None:
    review = _review_root(
        tmp_path / "review",
        [
            _record("MIT-1", "permissive-source", "MIT", "種類ごとに分けること"),
            _record(
                "NC-1",
                "noncommercial-source",
                "CC BY-NC-SA 3.0",
                "意味によって体系的に区分すること",
            ),
        ],
    )
    master = tmp_path / "master"
    public = tmp_path / "public"
    compile_canonical_dictionary(review, master, shard_size=100)
    manifest = compile_public_dictionary_view(master, public, shard_size=100)

    assert manifest["record_count"] == 1
    assert manifest["sense_count"] == 1
    assert manifest["license_exclusion_count"] >= 1
    assert manifest["boundaries"]["noncommercial_source_auto_promotion"] is False
    with gzip.open(
        public / "records/dictionary-0000.jsonl.gz", "rt", encoding="utf-8"
    ) as handle:
        row = json.loads(next(handle))
    assert len(row["senses"]) == 1
    assert row["senses"][0]["glosses"] == ["種類ごとに分けること"]
    assert {item["dataset"] for item in row["source_evidence"]} == {
        "permissive-source"
    }
    exclusions = [
        json.loads(line)
        for line in (public / "license-exclusions.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    assert any(item["source_record_id"] == "NC-1" for item in exclusions)


def test_public_view_drops_record_when_only_noncommercial_meaning_exists(
    tmp_path: Path,
) -> None:
    review = _review_root(
        tmp_path / "review",
        [
            _record(
                "NC-ONLY",
                "noncommercial-source",
                "CC BY-NC-SA 3.0",
                "非営利Sourceだけの意味",
            )
        ],
    )
    master = tmp_path / "master"
    public = tmp_path / "public"
    compile_canonical_dictionary(review, master, shard_size=100)
    manifest = compile_public_dictionary_view(master, public, shard_size=100)
    assert manifest["record_count"] == 0
    assert manifest["sense_count"] == 0
    assert manifest["license_exclusion_count"] >= 1
