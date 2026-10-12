from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.build_j_ono_pos_review_queue import build_pos_review_queue


def _record(record_id: str, source_id: str) -> dict:
    return {
        "adapter_record_id": record_id,
        "source": {"source_record_id": source_id},
        "surfaces": ["dummy"],
        "meanings": ["dummy meaning"],
    }


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def test_build_pos_review_queue_uses_references_only_and_preserves_review_boundaries(
    tmp_path: Path,
) -> None:
    records = [
        _record("A", "src-a"),
        _record("B", "src-b"),
        _record("C", "src-c"),
    ]
    evidence = [
        {
            "adapter_record_id": "A",
            "strong_status": "UNIQUE_STRONG_POS_EVIDENCE",
            "strong_candidate_pos": ["adverb (fukushi)"],
            "strong_open_lexicon_record_ids": ["JMD-A"],
            "strong_source_datasets": ["JMdict"],
        },
        {
            "adapter_record_id": "B",
            "strong_status": "AMBIGUOUS_STRONG_POS_EVIDENCE",
            "strong_candidate_pos": ["adverb (fukushi)", "noun (common) (futsuumeishi)"],
            "strong_open_lexicon_record_ids": ["JMD-B"],
            "strong_source_datasets": ["JMdict"],
        },
    ]
    records_path = tmp_path / "records.jsonl"
    evidence_path = tmp_path / "pos.jsonl"
    output_path = tmp_path / "queue.jsonl"
    report_path = tmp_path / "report.json"
    _write_jsonl(records_path, records)
    _write_jsonl(evidence_path, evidence)

    report = build_pos_review_queue(
        records_path=records_path,
        pos_evidence_path=evidence_path,
        output_path=output_path,
        report_path=report_path,
        expected_records=3,
        expected_buckets={
            "STRONG_UNIQUE_REVIEW_PRIORITY": 1,
            "STRONG_AMBIGUOUS_REVIEW_REQUIRED": 1,
            "NO_STRONG_EVIDENCE": 1,
        },
    )

    assert report["record_count"] == 3
    assert report["payload_model"] == "record-and-evidence-references-only"
    assert report["automatic_pos_fill"] is False
    assert report["automatic_approval"] is False
    assert report["runtime_promotion"] is False

    rows = [
        json.loads(line)
        for line in output_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_id = {row["adapter_record_id"]: row for row in rows}
    assert by_id["A"]["review_bucket"] == "STRONG_UNIQUE_REVIEW_PRIORITY"
    assert by_id["A"]["candidate_pos"] == ["adverb (fukushi)"]
    assert by_id["A"]["open_lexicon_record_ids"] == ["JMD-A"]
    assert by_id["B"]["review_bucket"] == "STRONG_AMBIGUOUS_REVIEW_REQUIRED"
    assert by_id["C"]["review_bucket"] == "NO_STRONG_EVIDENCE"
    for row in rows:
        assert "surfaces" not in row
        assert "meanings" not in row
        assert row["automatic_pos_fill"] is False
        assert row["automatic_approval"] is False
        assert row["runtime_promotion"] is False


def test_build_pos_review_queue_fails_closed_on_unknown_record(tmp_path: Path) -> None:
    records_path = tmp_path / "records.jsonl"
    evidence_path = tmp_path / "pos.jsonl"
    _write_jsonl(records_path, [_record("A", "src-a")])
    _write_jsonl(
        evidence_path,
        [{
            "adapter_record_id": "UNKNOWN",
            "strong_status": "UNIQUE_STRONG_POS_EVIDENCE",
            "strong_candidate_pos": ["noun"],
            "strong_open_lexicon_record_ids": ["JMD-X"],
            "strong_source_datasets": ["JMdict"],
        }],
    )

    with pytest.raises(ValueError, match="unknown record"):
        build_pos_review_queue(
            records_path=records_path,
            pos_evidence_path=evidence_path,
            output_path=tmp_path / "queue.jsonl",
            report_path=tmp_path / "report.json",
            expected_records=1,
            expected_buckets={
                "STRONG_UNIQUE_REVIEW_PRIORITY": 1,
                "STRONG_AMBIGUOUS_REVIEW_REQUIRED": 0,
                "NO_STRONG_EVIDENCE": 0,
            },
        )


def test_build_pos_review_queue_fails_closed_on_bucket_drift(tmp_path: Path) -> None:
    records_path = tmp_path / "records.jsonl"
    evidence_path = tmp_path / "pos.jsonl"
    _write_jsonl(records_path, [_record("A", "src-a")])
    _write_jsonl(evidence_path, [])

    with pytest.raises(ValueError, match="J_ONO_POS_REVIEW_BUCKET_COUNT_MISMATCH"):
        build_pos_review_queue(
            records_path=records_path,
            pos_evidence_path=evidence_path,
            output_path=tmp_path / "queue.jsonl",
            report_path=tmp_path / "report.json",
            expected_records=1,
            expected_buckets={
                "STRONG_UNIQUE_REVIEW_PRIORITY": 1,
                "STRONG_AMBIGUOUS_REVIEW_REQUIRED": 0,
                "NO_STRONG_EVIDENCE": 0,
            },
        )
