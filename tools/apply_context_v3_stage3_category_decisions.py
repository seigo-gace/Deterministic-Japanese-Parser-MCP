#!/usr/bin/env python3
"""Apply explicit Stage 3 category-review decisions without runtime promotion.

This tool consumes a Stage 3 queue after earlier decision layers. It applies
only checked-in decisions for one bounded category-review batch. It never
reclassifies an entry, invents a decision, or promotes runtime data.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable

ALLOWED_DECISIONS = {
    "reject-category-mismatch",
    "retain-category-for-evidence-review",
}
TARGET_INPUT_STATUS = "suspected-category-mismatch"
REJECTED_STATUS = "reviewed-rejected"
RETAINED_STATUS = "ready-for-human-evidence-review"
REQUIRED_FLAG = "name-or-place-candidate"
BATCH_ID_PATTERN = re.compile(r"^category-name-place-batch-(\d{3})$")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _jsonl(rows: Iterable[dict[str, Any]]) -> str:
    return "".join(_canonical_json(row) + "\n" for row in rows)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        line = raw.strip()
        if not line:
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(
                f"JSONL row must be an object: {path}:{line_number}"
            )
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


def _batch_prefix(batch_id: str) -> str:
    match = BATCH_ID_PATTERN.fullmatch(batch_id)
    if not match:
        raise ValueError(
            "batch_id must match category-name-place-batch-NNN: "
            f"{batch_id!r}"
        )
    return f"category-batch-{match.group(1)}"


def validate_decisions(
    decisions: list[dict[str, Any]],
    queue_by_id: dict[str, dict[str, Any]],
    expected_batch_size: int,
) -> tuple[dict[str, dict[str, Any]], str]:
    if len(decisions) != expected_batch_size:
        raise ValueError(
            "category decision batch size mismatch: "
            f"expected={expected_batch_size} actual={len(decisions)}"
        )

    required_fields = {
        "batch_id",
        "entry_id",
        "surface",
        "category",
        "decision",
        "reason_code",
        "rationale",
        "source_path",
        "source_pos",
        "observed_meaning",
        "review_mode",
        "reviewed_at",
        "runtime_promotion_allowed",
        "final_runtime_approval",
    }
    by_id: dict[str, dict[str, Any]] = {}
    batch_ids: set[str] = set()

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
        if decision["category"] != queue_item["category"]:
            raise ValueError(f"category mismatch for {entry_id}")
        if decision["source_path"] != queue_item["path"]:
            raise ValueError(f"source path mismatch for {entry_id}")
        if queue_item["primary_status"] != TARGET_INPUT_STATUS:
            raise ValueError(
                f"decision outside category-review scope: {entry_id} "
                f"status={queue_item['primary_status']}"
            )
        if REQUIRED_FLAG not in queue_item.get("flags", []):
            raise ValueError(f"required review flag missing: {entry_id}")
        if decision["decision"] not in ALLOWED_DECISIONS:
            raise ValueError(
                f"unsupported decision for {entry_id}: "
                f"{decision['decision']}"
            )
        if decision["runtime_promotion_allowed"] is not False:
            raise ValueError(f"decision attempts runtime promotion: {entry_id}")
        if decision["final_runtime_approval"] is not False:
            raise ValueError(f"final runtime approval is forbidden: {entry_id}")

        batch_ids.add(str(decision["batch_id"]).strip())
        by_id[entry_id] = decision

    if len(batch_ids) != 1 or "" in batch_ids:
        raise ValueError(f"exactly one non-empty batch_id is required: {batch_ids}")
    batch_id = next(iter(batch_ids))
    _batch_prefix(batch_id)
    return by_id, batch_id


def apply_decisions(
    queue: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    expected_batch_size: int,
) -> dict[str, str]:
    queue_by_id = validate_queue(queue)
    decisions_by_id, batch_id = validate_decisions(
        decisions, queue_by_id, expected_batch_size
    )
    output_prefix = _batch_prefix(batch_id)

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
                if decision["decision"] == "reject-category-mismatch"
                else RETAINED_STATUS
            )
            current["primary_status"] = next_status
            current["category_review"] = {
                "batch_id": decision["batch_id"],
                "decision": decision["decision"],
                "reason_code": decision["reason_code"],
                "rationale": decision["rationale"],
                "source_path": decision["source_path"],
                "source_pos": decision["source_pos"],
                "observed_meaning": decision["observed_meaning"],
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
            raise ValueError(
                f"runtime promotion boundary changed: {current['entry_id']}"
            )
        output_rows.append(current)

    after_counts = Counter(str(item["primary_status"]) for item in output_rows)
    decision_text = _jsonl(decisions)
    applied_text = _jsonl(applied_rows)
    queue_text = _jsonl(output_rows)
    summary = {
        "schema_version": "1.0.0",
        "stage": 3,
        "batch_id": batch_id,
        "review_scope": "name-or-place suspected category mismatch",
        "input_entries": len(queue),
        "explicit_decisions": len(decisions),
        "decision_counts": dict(sorted(decision_counts.items())),
        "status_counts_before": dict(sorted(before_counts.items())),
        "status_counts_after": dict(sorted(after_counts.items())),
        "remaining_suspected_category_mismatches": after_counts.get(
            TARGET_INPUT_STATUS, 0
        ),
        "reviewed_rejected_entries_total": after_counts.get(
            REJECTED_STATUS, 0
        ),
        "retained_for_evidence_review_in_batch": decision_counts.get(
            "retain-category-for-evidence-review", 0
        ),
        "rejected_category_mismatches_in_batch": decision_counts.get(
            "reject-category-mismatch", 0
        ),
        "runtime_promoted_entries": 0,
        "automatic_decision": False,
        "automatic_reclassification": False,
        "manual_decision_ledger_required": True,
        "decision_ledger_sha256": _sha256(decision_text),
        "applied_decisions_sha256": _sha256(applied_text),
    }
    boundary = {
        "stage": 3,
        "batch_id": batch_id,
        "name": "manual category mismatch review",
        "input_entries": len(queue),
        "explicit_decisions": len(decisions),
        "rejected_category_mismatches_in_batch": summary[
            "rejected_category_mismatches_in_batch"
        ],
        "retained_for_evidence_review_in_batch": summary[
            "retained_for_evidence_review_in_batch"
        ],
        "runtime_promoted_entries": 0,
        "automatic_approval": False,
        "automatic_rejection": False,
        "automatic_reclassification": False,
        "runtime_promotion_allowed": False,
        "next_transition": (
            "continue remaining category mismatches, then external-action, "
            "source/license, and direct evidence review"
        ),
    }
    return {
        f"{output_prefix}-summary.json": json.dumps(
            summary, ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n",
        f"post-{output_prefix}-queue.jsonl": queue_text,
        f"{output_prefix}-applied-decisions.jsonl": applied_text,
        f"runtime-boundary-after-{output_prefix}.json": json.dumps(
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
    parser.add_argument("--expected-batch-size", type=int, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    reports = apply_decisions(
        load_jsonl(args.queue),
        load_jsonl(args.decisions),
        args.expected_batch_size,
    )
    write_outputs(args.output_root, reports)
    summary_name = next(
        name for name in reports if name.endswith("-summary.json")
    )
    print(reports[summary_name], end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
