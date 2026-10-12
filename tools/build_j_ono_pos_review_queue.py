#!/usr/bin/env python3
"""Build a lightweight, review-only J-Ono POS evidence queue.

The queue references existing J-Ono adapter records and Open Lexicon record IDs.
It never copies full lexical payloads, assigns POS, approves records, or promotes
runtime data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

EXPECTED_RECORDS = 837
EXPECTED_BUCKETS = {
    "STRONG_UNIQUE_REVIEW_PRIORITY": 94,
    "STRONG_AMBIGUOUS_REVIEW_REQUIRED": 214,
    "NO_STRONG_EVIDENCE": 529,
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"row must be object: {path}:{line_number}")
            rows.append(row)
    return rows


def build_pos_review_queue(
    *,
    records_path: Path,
    pos_evidence_path: Path,
    output_path: Path,
    report_path: Path,
    expected_records: int = EXPECTED_RECORDS,
    expected_buckets: dict[str, int] | None = None,
) -> dict[str, Any]:
    records = _read_jsonl(records_path)
    evidence = _read_jsonl(pos_evidence_path)

    record_ids: list[str] = []
    source_ids: dict[str, str] = {}
    for index, row in enumerate(records, 1):
        record_id = str(row.get("adapter_record_id") or "").strip()
        if not record_id:
            raise ValueError(f"adapter_record_id missing at source row {index}")
        if record_id in source_ids:
            raise ValueError(f"duplicate adapter_record_id: {record_id}")
        record_ids.append(record_id)
        source = row.get("source") if isinstance(row.get("source"), dict) else {}
        source_ids[record_id] = str(source.get("source_record_id") or "").strip()

    if len(record_ids) != expected_records:
        raise ValueError(
            f"J_ONO_POS_REVIEW_SOURCE_COUNT_MISMATCH:"
            f"expected={expected_records}:actual={len(record_ids)}"
        )

    evidence_by_id: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(evidence, 1):
        record_id = str(row.get("adapter_record_id") or "").strip()
        if not record_id:
            raise ValueError(f"POS evidence adapter_record_id missing at row {index}")
        if record_id not in source_ids:
            raise ValueError(f"POS evidence references unknown record: {record_id}")
        if record_id in evidence_by_id:
            raise ValueError(f"duplicate POS evidence record: {record_id}")
        evidence_by_id[record_id] = row

    output_rows: list[dict[str, Any]] = []
    bucket_counts = {key: 0 for key in EXPECTED_BUCKETS}
    for record_id in sorted(record_ids):
        row = evidence_by_id.get(record_id) or {}
        status = str(row.get("strong_status") or "NO_STRONG_POS_EVIDENCE")
        candidate_pos = sorted({
            str(value).strip()
            for value in row.get("strong_candidate_pos") or []
            if str(value).strip()
        })
        open_lexicon_ids = sorted({
            str(value).strip()
            for value in row.get("strong_open_lexicon_record_ids") or []
            if str(value).strip()
        })
        source_datasets = sorted({
            str(value).strip()
            for value in row.get("strong_source_datasets") or []
            if str(value).strip()
        })

        if status == "UNIQUE_STRONG_POS_EVIDENCE":
            if len(candidate_pos) != 1 or not open_lexicon_ids:
                raise ValueError(f"invalid unique strong POS evidence: {record_id}")
            bucket = "STRONG_UNIQUE_REVIEW_PRIORITY"
        elif status == "AMBIGUOUS_STRONG_POS_EVIDENCE":
            if len(candidate_pos) < 2 or not open_lexicon_ids:
                raise ValueError(f"invalid ambiguous strong POS evidence: {record_id}")
            bucket = "STRONG_AMBIGUOUS_REVIEW_REQUIRED"
        elif status == "NO_STRONG_POS_EVIDENCE":
            if candidate_pos or open_lexicon_ids:
                raise ValueError(f"no-strong POS row contains strong candidates: {record_id}")
            bucket = "NO_STRONG_EVIDENCE"
        else:
            raise ValueError(f"unknown strong POS evidence status: {status}")

        bucket_counts[bucket] += 1
        output_rows.append({
            "adapter_record_id": record_id,
            "source_record_id": source_ids[record_id],
            "review_bucket": bucket,
            "candidate_pos": candidate_pos,
            "open_lexicon_record_ids": open_lexicon_ids,
            "source_datasets": source_datasets,
            "evidence_contract": "surface+source-reading exact match against existing Open Lexicon",
            "automatic_pos_fill": False,
            "automatic_approval": False,
            "runtime_promotion": False,
        })

    expected = expected_buckets or EXPECTED_BUCKETS
    if bucket_counts != expected:
        raise ValueError(
            "J_ONO_POS_REVIEW_BUCKET_COUNT_MISMATCH:"
            f"expected={json.dumps(expected, sort_keys=True)}:"
            f"actual={json.dumps(bucket_counts, sort_keys=True)}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in output_rows:
            handle.write(
                json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n"
            )

    report = {
        "status": "J_ONO_POS_REVIEW_QUEUE_READY",
        "record_count": len(output_rows),
        "bucket_counts": bucket_counts,
        "source_records_sha256": _sha256_file(records_path),
        "pos_evidence_sha256": _sha256_file(pos_evidence_path),
        "payload_model": "record-and-evidence-references-only",
        "automatic_pos_fill": False,
        "automatic_approval": False,
        "runtime_promotion": False,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--pos-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = build_pos_review_queue(
        records_path=args.records,
        pos_evidence_path=args.pos_evidence,
        output_path=args.output,
        report_path=args.report,
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
