#!/usr/bin/env python3
"""Verify whether exact GPT CHAT J-Ono semantic decisions are already canonical.

This verifier is read-only. It never writes or applies decisions. It is used to
make the review audit idempotent after the exact authorized decisions are added
to the canonical Decision Ledger.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import hashlib
from typing import Any

try:
    from tools.prepare_j_ono_chat_semantic_decisions import (
        _decision_for,
        _read_json,
        _read_jsonl,
        _validate_record,
    )
except ModuleNotFoundError:  # direct execution: python tools/verify_*.py
    from prepare_j_ono_chat_semantic_decisions import (
        _decision_for,
        _read_json,
        _read_jsonl,
        _validate_record,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_existing_decisions(
    review_queue: Path,
    authorization_path: Path,
    existing_ledger_path: Path,
    effectiveness_report_path: Path | None = None,
    review_audit_report_path: Path | None = None,
) -> dict[str, Any]:
    authorization = _read_json(authorization_path)
    if _sha256(review_queue) != str(authorization["review_queue_sha256"]):
        raise ValueError("J_ONO_CHAT_EXISTING_VERIFY_QUEUE_DIGEST_MISMATCH")
    if effectiveness_report_path is not None and _sha256(
        effectiveness_report_path
    ) != str(authorization["source_evidence_effectiveness_report_sha256"]):
        raise ValueError(
            "J_ONO_CHAT_EXISTING_VERIFY_EFFECTIVENESS_DIGEST_MISMATCH"
        )
    if review_audit_report_path is not None and _sha256(
        review_audit_report_path
    ) != str(authorization["review_audit_report_sha256"]):
        raise ValueError("J_ONO_CHAT_EXISTING_VERIFY_AUDIT_DIGEST_MISMATCH")
    rows = _read_jsonl(review_queue)
    expected_records = int(authorization["expected_record_count"])
    if len(rows) != expected_records:
        raise ValueError(
            "J_ONO_CHAT_EXISTING_VERIFY_RECORD_COUNT_MISMATCH:"
            f"expected={expected_records}:actual={len(rows)}"
        )
    candidate_count = sum(_validate_record(row) for row in rows)
    if candidate_count != int(authorization["expected_meaning_candidate_count"]):
        raise ValueError("J_ONO_CHAT_EXISTING_VERIFY_CANDIDATE_COUNT_MISMATCH")

    reviewer = str(authorization["reviewer"])
    decided_at = str(authorization["decided_at"])
    expected = {
        str(item["record_id"]): item
        for item in (
            _decision_for(record, reviewer=reviewer, decided_at=decided_at)
            for record in sorted(rows, key=lambda value: str(value["record_id"]))
        )
    }
    ledger = _read_jsonl(existing_ledger_path)
    relevant = [
        {
            key: value
            for key, value in item.items()
            if not key.startswith("_")
        }
        for item in ledger
        if str(item.get("record_id") or "") in expected
        and str(item.get("scope") or "") == "semantic"
    ]

    if not relevant:
        status = "NOT_APPLIED"
        exact_count = 0
    else:
        if len(relevant) != expected_records:
            raise ValueError(
                "J_ONO_CHAT_EXISTING_VERIFY_PARTIAL_DECISIONS:"
                f"expected={expected_records}:actual={len(relevant)}"
            )
        by_record = {str(item["record_id"]): item for item in relevant}
        if set(by_record) != set(expected):
            raise ValueError("J_ONO_CHAT_EXISTING_VERIFY_RECORD_SET_MISMATCH")
        mismatched = [
            rid
            for rid, item in expected.items()
            if by_record[rid] != item
        ]
        if mismatched:
            raise ValueError(
                "J_ONO_CHAT_EXISTING_VERIFY_DECISION_MISMATCH:"
                + ",".join(mismatched[:20])
            )
        status = "ALREADY_APPLIED"
        exact_count = len(relevant)

    return {
        "status": status,
        "expected_record_count": expected_records,
        "meaning_candidate_count": candidate_count,
        "existing_exact_semantic_decision_count": exact_count,
        "new_semantic_decision_required": status == "NOT_APPLIED",
        "lexical_approval": False,
        "automatic_approval": False,
        "decision_application": False,
        "runtime_promotion": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-queue", type=Path, required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--existing-ledger", type=Path, required=True)
    parser.add_argument("--effectiveness-report", type=Path)
    parser.add_argument("--review-audit-report", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = verify_existing_decisions(
        args.review_queue,
        args.authorization,
        args.existing_ledger,
        args.effectiveness_report,
        args.review_audit_report,
    )
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
