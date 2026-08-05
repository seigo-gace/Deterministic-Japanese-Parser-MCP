#!/usr/bin/env python3
"""Apply explicit Stage 3 review decisions without promoting runtime data.

The input queue is produced by ``review_context_v3_stage3.py``. This tool never
invents decisions: every state change must be present in the checked-in manual
decision ledger. It validates identity, surface, review scope, and runtime
boundaries before producing a deterministic post-decision queue and summary.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

ALLOWED_DECISIONS = {
    "reject-substring-artifact",
    "retain-for-evidence-review",
}
TARGET_INPUT_STATUS = "suspected-substring-artifact"
REJECTED_STATUS = "reviewed-rejected"
RETAINED_STATUS = "ready-for-human-evidence-review"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _jsonl(rows: Iterable[dict[str, Any]]) -> str:
    return "".join(_canonical_json(row) + "\n" for row in rows)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"JSONL row must be an object: {path}:{line_number}")
        rows.append(value)
    return rows


def validate_queue(queue: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for item in queue:
        entry_id = str(item.get("entry_id", "")).strip()
        surface = str(item.get("surface", "")).strip()
        if not entry_id or not surface:
            raise ValueError("queue entry_id and surface are required")
        if entry_id in by_id:
            raise ValueError(f"duplicate queue entry_id: {entry_id}")
        if item.get("runtime_promotion_allowed") is not False:
            raise ValueError(f"runtime boundary missing in queue: {entry_id}")
        by_id[entry_id] = item
    return by_id


def validate_decisions(
    decisions: list[dict[str, Any]],
    queue_by_id: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    required_fields = {
        "entry_id",
        "surface",
        "decision",
        "reason_code",
        "rationale",
        "review_mode",
        "reviewed_at",
        "runtime_promotion_allowed",
    }
    for decision in decisions:
        missing = sorted(required_fields - set(decision))
        if missing:
            raise ValueError(f"decision fields missing: {missing}")
        entry_id = str(decision["entry_id"]).strip()
        if entry_id in by_id:
            raise ValueError(f"duplicate decision entry_id: {entry_id}")
        if entry_id not in queue_by_id:
            raise ValueError(f"decision entry_id is not in queue: {entry_id}")
        queue_item = queue_by_id[entry_id]
        if decision["surface"] != queue_item["surface"]:
            raise ValueError(f"surface mismatch for {entry_id}")
        if queue_item["primary_status"] != TARGET_INPUT_STATUS:
            raise ValueError(
                f"decision outside substring-review scope: {entry_id} "
                f"status={queue_item['primary_status']}"
            )
        if decision["decision"] not in ALLOWED_DECISIONS:
            raise ValueError(f"unsupported decision for {entry_id}: {decision['decision']}")
        if decision["runtime_promotion_allowed"] is not False:
            raise ValueError(f"decision attempts runtime promotion: {entry_id}")
        if decision.get("final_runtime_approval") not in (None, False):
            raise ValueError(f"final runtime approval is forbidden: {entry_id}")
        by_id[entry_id] = decision

    expected = {
        entry_id
        for entry_id, item in queue_by_id.items()
        if item["primary_status"] == TARGET_INPUT_STATUS
    }
    actual = set(by_id)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise ValueError(
            f"substring decision coverage mismatch: missing={missing[:10]} "
            f"unexpected={unexpected[:10]}"
        )
    return by_id


def apply_decisions(
    queue: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
) -> dict[str, str]:
    queue_by_id = validate_queue(queue)
    decisions_by_id = validate_decisions(decisions, queue_by_id)

    before_counts = Counter(str(item["primary_status"]) for item in queue)
    decision_counts = Counter(str(item["decision"]) for item in decisions)
    output_rows: list[dict[str, Any]] = []
    applied_rows: list[dict[str, Any]] = []

    for item in queue:
        current = dict(item)
        decision = decisions_by_id.get(str(item["entry_id"]))
        if decision:
            next_status = (
                REJECTED_STATUS
                if decision["decision"] == "reject-substring-artifact"
                else RETAINED_STATUS
            )
            current["primary_status"] = next_status
            current["manual_review"] = {
                "decision": decision["decision"],
                "reason_code": decision["reason_code"],
                "rationale": decision["rationale"],
                "review_mode": decision["review_mode"],
                "reviewed_at": decision["reviewed_at"],
                "final_runtime_approval": False,
            }
            applied_rows.append(
                {
                    **decision,
                    "previous_status": TARGET_INPUT_STATUS,
                    "next_status": next_status,
                    "final_runtime_approval": False,
                }
            )
        if current.get("runtime_promotion_allowed") is not False:
            raise ValueError(f"runtime promotion boundary changed: {current['entry_id']}")
        output_rows.append(current)

    after_counts = Counter(str(item["primary_status"]) for item in output_rows)
    queue_text = _jsonl(output_rows)
    applied_text = _jsonl(applied_rows)
    source_decisions_text = _jsonl(decisions)
    summary = {
        "schema_version": "1.0.0",
        "stage": 3,
        "review_scope": "epistemic substring artifacts",
        "input_entries": len(queue),
        "explicit_decisions": len(decisions),
        "decision_counts": dict(sorted(decision_counts.items())),
        "status_counts_before": dict(sorted(before_counts.items())),
        "status_counts_after": dict(sorted(after_counts.items())),
        "remaining_suspected_substring_artifacts": after_counts.get(
            TARGET_INPUT_STATUS, 0
        ),
        "reviewed_rejected_entries": after_counts.get(REJECTED_STATUS, 0),
        "retained_for_evidence_review": decision_counts.get(
            "retain-for-evidence-review", 0
        ),
        "runtime_promoted_entries": 0,
        "automatic_decision": False,
        "manual_decision_ledger_required": True,
        "decision_ledger_sha256": _sha256(source_decisions_text),
        "applied_decisions_sha256": _sha256(applied_text),
        "post_decision_queue_sha256": _sha256(queue_text),
    }
    boundary = {
        "stage": 3,
        "name": "manual substring-artifact review",
        "input_entries": len(queue),
        "explicit_decisions": len(decisions),
        "reviewed_rejected_entries": summary["reviewed_rejected_entries"],
        "retained_for_evidence_review": summary["retained_for_evidence_review"],
        "runtime_promoted_entries": 0,
        "automatic_approval": False,
        "automatic_rejection": False,
        "runtime_promotion_allowed": False,
        "next_transition": (
            "category mismatch review, then source/license and evidence review"
        ),
    }
    return {
        "decision-summary.json": json.dumps(
            summary, ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n",
        "post-decision-queue.jsonl": queue_text,
        "applied-decisions.jsonl": applied_text,
        "runtime-boundary-after-decisions.json": json.dumps(
            boundary, ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n",
    }


def write_outputs(output_root: Path, reports: dict[str, str]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    for name, content in reports.items():
        (output_root / name).write_text(content, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    reports = apply_decisions(load_jsonl(args.queue), load_jsonl(args.decisions))
    write_outputs(args.output_root, reports)
    print(reports["decision-summary.json"], end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
