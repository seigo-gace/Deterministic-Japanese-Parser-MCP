from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.measure_j_ono_source_evidence_effectiveness import (
    measure_source_evidence_effectiveness,
)


def _member(
    record_id: str,
    *,
    equivalents: list[str] | None = None,
    semantic_type_code: str = "",
    refer: str = "",
    resolved: list[dict] | None = None,
    example_file: str = "",
) -> dict:
    return {
        "record_id": record_id,
        "source_evidence": {
            "equivalents": equivalents or [],
            "semantic_type_code": semantic_type_code,
            "semantic_type_label": "",
            "refer": refer,
            "resolved_meaning_evidence": resolved or [],
            "example_metadata": (
                [{
                    "source": "src",
                    "file": example_file,
                    "display": "inline",
                    "contributor": "",
                }]
                if example_file
                else []
            ),
        },
    }


def _write_clusters(path: Path, clusters: list[dict]) -> None:
    path.write_text(
        "".join(
            json.dumps(cluster, ensure_ascii=False, sort_keys=True) + "\n"
            for cluster in clusters
        ),
        encoding="utf-8",
    )


def test_semantic_evidence_reduces_ambiguity_without_counting_example_metadata_as_semantics(
    tmp_path: Path,
) -> None:
    path = tmp_path / "clusters.jsonl"
    _write_clusters(
        path,
        [{
            "cluster_id": "c1",
            "reading_partition_count": 1,
            "members": [
                _member("a", equivalents=["sparkle"], semantic_type_code="m", example_file="a.png"),
                _member("b", equivalents=["menace"], semantic_type_code="e", example_file="b.png"),
                _member("c", equivalents=["menace"], semantic_type_code="e", example_file="c.png"),
            ],
        }],
    )

    report, details = measure_source_evidence_effectiveness(
        path,
        expected_reading_unresolved=1,
    )

    assert report["reading_unresolved_cluster_count"] == 1
    assert report["semantic_evidence"]["total_pairs"] == 3
    assert report["semantic_evidence"]["distinguished_pairs"] == 2
    assert report["semantic_evidence"]["pair_reduction_ratio"] == pytest.approx(2 / 3, abs=1e-6)
    assert report["all_source_evidence"]["distinguished_pairs"] == 3
    assert report["provenance_only_extra_distinguished_pairs"] == 1
    assert report["interpretation_boundary"][
        "example_metadata_excluded_from_primary_semantic_score"
    ] is True
    assert details[0]["automatic_merge"] is False
    assert details[0]["automatic_meaning_judgement"] is False
    assert details[0]["automatic_pos_fill"] is False
    assert details[0]["runtime_promotion"] is False


def test_missing_vs_present_semantic_evidence_is_not_counted_as_semantic_truth(
    tmp_path: Path,
) -> None:
    path = tmp_path / "clusters.jsonl"
    _write_clusters(
        path,
        [{
            "cluster_id": "c1",
            "reading_partition_count": 1,
            "members": [
                _member("a", equivalents=["sparkle"]),
                _member("b"),
            ],
        }],
    )

    report, _ = measure_source_evidence_effectiveness(
        path,
        expected_reading_unresolved=1,
    )

    assert report["semantic_evidence"]["total_pairs"] == 1
    assert report["semantic_evidence"]["distinguished_pairs"] == 0
    assert report["semantic_evidence"]["availability_difference_pairs"] == 1
    assert report["interpretation_boundary"][
        "missing_vs_present_evidence_not_counted_as_semantic_disambiguation"
    ] is True


def test_reading_unresolved_cluster_count_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "clusters.jsonl"
    _write_clusters(
        path,
        [{
            "cluster_id": "c1",
            "reading_partition_count": 2,
            "members": [_member("a"), _member("b")],
        }],
    )

    with pytest.raises(
        ValueError,
        match="J_ONO_READING_UNRESOLVED_CLUSTER_COUNT_MISMATCH",
    ):
        measure_source_evidence_effectiveness(
            path,
            expected_reading_unresolved=1,
        )


def test_local_source_identity_is_not_counted_as_refer_disambiguation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "clusters.jsonl"
    _write_clusters(
        path,
        [{
            "cluster_id": "c1",
            "reading_partition_count": 1,
            "members": [
                _member(
                    "a",
                    resolved=[{
                        "source_record_id": "local-a",
                        "source_definition_index": 1,
                        "meaning": "x",
                        "via_refer": False,
                    }],
                ),
                _member(
                    "b",
                    resolved=[{
                        "source_record_id": "local-b",
                        "source_definition_index": 1,
                        "meaning": "y",
                        "via_refer": False,
                    }],
                ),
            ],
        }],
    )

    report, _ = measure_source_evidence_effectiveness(
        path,
        expected_reading_unresolved=1,
    )

    refer = report["dimension_totals"]["refer_provenance"]
    assert refer["distinguished_pairs"] == 0
    assert report["semantic_evidence"]["distinguished_pairs"] == 0


def test_real_refer_path_can_be_counted_as_review_signal(tmp_path: Path) -> None:
    path = tmp_path / "clusters.jsonl"
    _write_clusters(
        path,
        [{
            "cluster_id": "c1",
            "reading_partition_count": 1,
            "members": [
                _member(
                    "a",
                    refer="target-a:1",
                    resolved=[{
                        "source_record_id": "target-a",
                        "source_definition_index": 1,
                        "meaning": "x",
                        "via_refer": True,
                    }],
                ),
                _member(
                    "b",
                    refer="target-b:1",
                    resolved=[{
                        "source_record_id": "target-b",
                        "source_definition_index": 1,
                        "meaning": "y",
                        "via_refer": True,
                    }],
                ),
            ],
        }],
    )

    report, _ = measure_source_evidence_effectiveness(
        path,
        expected_reading_unresolved=1,
    )

    assert report["dimension_totals"]["refer_provenance"]["distinguished_pairs"] == 1
    assert report["semantic_evidence"]["distinguished_pairs"] == 1
