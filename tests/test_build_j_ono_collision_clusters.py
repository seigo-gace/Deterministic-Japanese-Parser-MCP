from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.build_j_ono_collision_clusters import (
    EXPECTED_CLUSTERS,
    EXPECTED_RECORDS,
    build_clusters,
)


def _row(i: int) -> dict:
    return {
        "adapter_record_id": f"FROZEN-j-ono-definitions-{i:024d}",
        "source_role": "lexical-definition",
        "surfaces": [f"surface-{i}"],
        "readings": [f"reading-{i}"],
        "part_of_speech_list": [],
        "meanings": [f"meaning-{i}"],
        "source": {
            "dataset": "j-ono-definitions",
            "logical_source_id": "j-ono-definitions",
            "source_record_id": f"j-ono:{i}",
            "public_runtime_eligible": True,
        },
        "payload": {
            "j_ono_source_evidence": {
                "local_meaning": f"meaning-{i}",
                "equivalents": [f"equivalent-{i}"],
                "refer": "",
                "semantic_type_code": "m",
                "semantic_type_label": "state-manner",
                "resolved_meaning_evidence": [],
                "example_metadata": [],
                "automatic_semantic_interpretation": False,
            }
        },
    }


def _write_records(path: Path) -> None:
    path.write_text(
        "".join(json.dumps(_row(i), ensure_ascii=False) + "\n" for i in range(EXPECTED_RECORDS)),
        encoding="utf-8",
    )


def _write_issues(path: Path) -> None:
    lines = []
    for i in range(EXPECTED_CLUSTERS):
        a = f"FROZEN-j-ono-definitions-{(i * 2):024d}"
        b = f"FROZEN-j-ono-definitions-{(i * 2 + 1):024d}"
        lines.append({
            "kind": "SURFACE_COLLISION_DIVERGENT_MEANING",
            "severity": "review",
            "surface": f"shared-{i}",
            "record_ids": [a, b],
        })
        lines.append({
            "kind": "SURFACE_COLLISION_DIVERGENT_MEANING",
            "severity": "review",
            "surface": f"variant-{i}",
            "record_ids": [b, a],
        })
    path.write_text(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines),
        encoding="utf-8",
    )


def test_build_clusters_groups_surface_variants_by_record_set(tmp_path: Path):
    records = tmp_path / "records.jsonl"
    issues = tmp_path / "issues.jsonl"
    _write_records(records)
    _write_issues(issues)
    report, clusters = build_clusters(records, issues)
    assert report["cluster_count"] == EXPECTED_CLUSTERS
    assert report["divergent_meaning_cluster_count"] == EXPECTED_CLUSTERS
    assert report["same_meaning_cluster_count"] == 0
    assert report["automatic_merge"] is False
    assert report["runtime_promotion"] is False
    assert len(clusters[0]["record_ids"]) == 2
    assert clusters[0]["variant_surface_count"] == 2
    assert clusters[0]["review_required"] is True
    assert clusters[0]["automatic_meaning_judgement"] is False
    assert clusters[0]["reading_partition_count"] == 2
    assert clusters[0]["reading_evidence_disambiguates_some_members"] is True
    assert clusters[0]["missing_reading_evidence"] is False
    assert clusters[0]["members"][0]["source_evidence"]["automatic_semantic_interpretation"] is False
    assert clusters[0]["members"][0]["source_evidence"]["equivalents"]
    assert report["clusters_with_distinct_reading_evidence"] == EXPECTED_CLUSTERS
    assert report["clusters_with_missing_reading_evidence"] == 0


def test_cluster_id_is_stable_when_issue_record_order_changes(tmp_path: Path):
    records = tmp_path / "records.jsonl"
    issues = tmp_path / "issues.jsonl"
    _write_records(records)
    _write_issues(issues)
    _, clusters_a = build_clusters(records, issues)
    raw = [json.loads(x) for x in issues.read_text(encoding="utf-8").splitlines() if x.strip()]
    for item in raw:
        item["record_ids"] = list(reversed(item["record_ids"]))
    issues.write_text("".join(json.dumps(x) + "\n" for x in raw), encoding="utf-8")
    _, clusters_b = build_clusters(records, issues)
    assert [x["cluster_id"] for x in clusters_a] == [x["cluster_id"] for x in clusters_b]


def test_cluster_build_fails_closed_on_unknown_record(tmp_path: Path):
    records = tmp_path / "records.jsonl"
    issues = tmp_path / "issues.jsonl"
    _write_records(records)
    _write_issues(issues)
    first = json.loads(issues.read_text(encoding="utf-8").splitlines()[0])
    first["record_ids"][0] = "UNKNOWN"
    issues.write_text(json.dumps(first) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="J_ONO_CLUSTER_UNKNOWN_RECORD"):
        build_clusters(records, issues)
