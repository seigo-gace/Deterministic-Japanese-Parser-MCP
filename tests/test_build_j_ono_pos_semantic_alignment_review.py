from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools.build_j_ono_pos_semantic_alignment_review import build_alignment_review


def _write_jsonl(path: Path, rows: list[dict]) -> str:
    payload = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        for row in rows
    )
    path.write_text(payload, encoding="utf-8")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _jono(record_id: str, source_id: str, meaning: str) -> dict:
    return {
        "adapter_record_id": record_id,
        "source_role": "lexical-definition",
        "meanings": [meaning],
        "source": {"source_record_id": source_id},
        "payload": {
            "j_ono_source_evidence": {
                "resolved_meaning_evidence": [{
                    "meaning": meaning,
                    "source_record_id": source_id.split(":")[0],
                    "source_definition_index": 1,
                    "via_refer": False,
                }],
                "equivalents": [],
                "semantic_type_code": "m",
                "semantic_type_label": "mimetic",
                "refer": "",
            }
        },
    }


def _pr26(record_id: str, pos: str, gloss: str) -> dict:
    return {
        "record_id": record_id,
        "lemma": record_id,
        "readings": ["てすと"],
        "part_of_speech": [pos],
        "meaning_candidates": [{
            "candidate_id": f"{record_id}:sense:001",
            "glosses": [gloss],
            "part_of_speech": [pos],
            "evidence_ids": [f"jmdict:{record_id}:sense:001"],
            "source": {
                "source_id": record_id,
                "source_sha256": "a" * 64,
            },
        }],
    }


def test_build_alignment_review_is_review_only_and_checksum_bound(tmp_path: Path) -> None:
    jono_path = tmp_path / "jono.jsonl"
    pos_path = tmp_path / "pos.jsonl"
    pr26_path = tmp_path / "pr26.jsonl"
    _write_jsonl(
        jono_path,
        [
            _jono("JONO-A", "a:001", "sharp click"),
            _jono("JONO-B", "b:001", "surprised gasp"),
            _jono("JONO-C", "c:001", "unresolved"),
        ],
    )
    _write_jsonl(
        pos_path,
        [
            {
                "adapter_record_id": "JONO-A",
                "review_bucket": "STRONG_UNIQUE_REVIEW_PRIORITY",
                "candidate_pos": ["adverb"],
                "open_lexicon_record_ids": ["JMD-A"],
            },
            {
                "adapter_record_id": "JONO-B",
                "review_bucket": "STRONG_UNIQUE_REVIEW_PRIORITY",
                "candidate_pos": ["interjection"],
                "open_lexicon_record_ids": ["JMD-B"],
            },
            {
                "adapter_record_id": "JONO-C",
                "review_bucket": "NO_STRONG_EVIDENCE",
                "candidate_pos": [],
                "open_lexicon_record_ids": [],
            },
        ],
    )
    pr26_sha = _write_jsonl(
        pr26_path,
        [
            _pr26("JMD-A", "adverb", "with a click"),
            _pr26("JMD-B", "interjection", "oh!"),
            _pr26("UNRELATED", "noun", "unused"),
        ],
    )

    output = tmp_path / "alignment.jsonl"
    report_path = tmp_path / "report.json"
    report = build_alignment_review(
        jono_records_path=jono_path,
        pos_review_queue_path=pos_path,
        pr26_review_queue_path=pr26_path,
        output_path=output,
        report_path=report_path,
        expected_pr26_sha256=pr26_sha,
        expected_jono_records=3,
        expected_priority_records=2,
        expected_distinct_jmdict_records=2,
    )

    assert report["review_record_count"] == 2
    assert report["distinct_jmdict_record_count"] == 2
    assert report["jmdict_sense_candidate_count"] == 2
    assert report["pr26_review_queue_sha256"] == pr26_sha
    assert report["semantic_alignment_judgement"] is False
    assert report["automatic_pos_fill"] is False
    assert report["automatic_approval"] is False
    assert report["runtime_promotion"] is False

    rows = [
        json.loads(line)
        for line in output.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 2
    assert {row["adapter_record_id"] for row in rows} == {"JONO-A", "JONO-B"}
    for row in rows:
        assert row["semantic_alignment_status"] == "NEEDS_EXPLICIT_REVIEW"
        assert row["automatic_semantic_alignment"] is False
        assert row["automatic_pos_fill"] is False
        assert row["automatic_approval"] is False
        assert row["runtime_promotion"] is False
        assert "surfaces" not in row
        assert "payload" not in row


def test_build_alignment_review_fails_closed_on_pr26_digest_mismatch(
    tmp_path: Path,
) -> None:
    jono_path = tmp_path / "jono.jsonl"
    pos_path = tmp_path / "pos.jsonl"
    pr26_path = tmp_path / "pr26.jsonl"
    _write_jsonl(jono_path, [_jono("JONO-A", "a:001", "click")])
    _write_jsonl(
        pos_path,
        [{
            "adapter_record_id": "JONO-A",
            "review_bucket": "STRONG_UNIQUE_REVIEW_PRIORITY",
            "candidate_pos": ["adverb"],
            "open_lexicon_record_ids": ["JMD-A"],
        }],
    )
    _write_jsonl(pr26_path, [_pr26("JMD-A", "adverb", "with a click")])

    with pytest.raises(
        ValueError,
        match="J_ONO_POS_ALIGNMENT_PR26_QUEUE_DIGEST_MISMATCH",
    ):
        build_alignment_review(
            jono_records_path=jono_path,
            pos_review_queue_path=pos_path,
            pr26_review_queue_path=pr26_path,
            output_path=tmp_path / "out.jsonl",
            report_path=tmp_path / "report.json",
            expected_pr26_sha256="0" * 64,
            expected_jono_records=1,
            expected_priority_records=1,
            expected_distinct_jmdict_records=1,
        )


def test_build_alignment_review_fails_closed_on_pos_drift(tmp_path: Path) -> None:
    jono_path = tmp_path / "jono.jsonl"
    pos_path = tmp_path / "pos.jsonl"
    pr26_path = tmp_path / "pr26.jsonl"
    _write_jsonl(jono_path, [_jono("JONO-A", "a:001", "click")])
    _write_jsonl(
        pos_path,
        [{
            "adapter_record_id": "JONO-A",
            "review_bucket": "STRONG_UNIQUE_REVIEW_PRIORITY",
            "candidate_pos": ["adverb"],
            "open_lexicon_record_ids": ["JMD-A"],
        }],
    )
    pr26_sha = _write_jsonl(pr26_path, [_pr26("JMD-A", "noun", "click")])

    with pytest.raises(ValueError, match="J_ONO_POS_ALIGNMENT_POS_DRIFT"):
        build_alignment_review(
            jono_records_path=jono_path,
            pos_review_queue_path=pos_path,
            pr26_review_queue_path=pr26_path,
            output_path=tmp_path / "out.jsonl",
            report_path=tmp_path / "report.json",
            expected_pr26_sha256=pr26_sha,
            expected_jono_records=1,
            expected_priority_records=1,
            expected_distinct_jmdict_records=1,
        )
