from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.audit_j_ono_data_quality import EXPECTED_RECORDS, audit_records


def _row(i: int) -> dict:
    return {
        "adapter_record_id": f"FROZEN-j-ono-definitions-{i:024d}",
        "source_role": "lexical-definition",
        "surfaces": [f"語{i}"],
        "readings": [f"ご{i}"],
        "part_of_speech_list": ["擬態"],
        "meanings": [f"意味{i}"],
        "source": {
            "dataset": "j-ono-definitions",
            "logical_source_id": "j-ono-definitions",
            "version": "1",
            "license": "test",
            "source_id": f"j-ono:{i}",
            "source_url": "https://example.invalid",
            "source_sha256": "a" * 64,
            "public_runtime_eligible": True,
        },
        "payload": {},
    }


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_audit_accepts_structurally_sound_837_and_reports_metrics(tmp_path: Path):
    path = tmp_path / "j-ono.jsonl"
    _write(path, [_row(i) for i in range(EXPECTED_RECORDS)])
    report, issues = audit_records(path)
    assert report["record_count"] == EXPECTED_RECORDS
    assert report["reading_coverage_records"] == EXPECTED_RECORDS
    assert report["pos_coverage_records"] == EXPECTED_RECORDS
    assert report["hard_failure_count"] == 0
    assert report["automatic_meaning_judgement"] is False
    assert report["automatic_approval"] is False
    assert issues == []


def test_audit_reports_review_flags_without_auto_rejecting_ambiguity(tmp_path: Path):
    rows = [_row(i) for i in range(EXPECTED_RECORDS)]
    rows[0]["readings"] = []
    rows[1]["part_of_speech_list"] = []
    rows[2]["meanings"] = [rows[2]["surfaces"][0]]
    rows[3]["surfaces"] = rows[4]["surfaces"]
    path = tmp_path / "j-ono.jsonl"
    _write(path, rows)
    report, issues = audit_records(path)
    kinds = {issue["kind"] for issue in issues}
    assert {"MISSING_READING", "MISSING_POS", "SELF_DEFINITION", "SURFACE_COLLISION_DIVERGENT_MEANING"} <= kinds
    assert report["review_issue_count"] >= 4
    assert report["hard_failure_count"] == 0


def test_audit_fails_closed_on_invalid_unicode(tmp_path: Path):
    rows = [_row(i) for i in range(EXPECTED_RECORDS)]
    rows[0]["meanings"] = ["壊れた�定義"]
    path = tmp_path / "j-ono.jsonl"
    _write(path, rows)
    with pytest.raises(ValueError, match="J_ONO_INVALID_UNICODE"):
        audit_records(path)


def test_audit_fails_closed_on_count_mismatch(tmp_path: Path):
    path = tmp_path / "j-ono.jsonl"
    _write(path, [_row(1)])
    with pytest.raises(ValueError, match="J_ONO_COUNT_MISMATCH"):
        audit_records(path)
