#!/usr/bin/env python3
"""Aggregate reviewed-but-evidence-pending records without promoting them.

The primary input is a reviewed data directory containing Decision Ledger JSON/JSONL
files. `needs-evidence` decisions are grouped by record. If a license report is present,
blocked license rows are represented as the lexical pending scope as well.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator

DECISION_SCOPES = {"semantic", "pragmatic", "task", "external_action"}
SCOPE_ORDER = ("lexical", "pragmatic", "semantic", "task", "external_action")


def _iter_json_values(path: Path) -> Iterator[dict[str, Any]]:
    if path.suffix == ".jsonl":
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    value = json.loads(line)
                    if isinstance(value, dict):
                        yield value
        return
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, list):
        yield from (item for item in value if isinstance(item, dict))
    elif isinstance(value, dict):
        rows = value.get("decisions")
        if isinstance(rows, list):
            yield from (item for item in rows if isinstance(item, dict))


def extract(input_root: Path, output_path: Path) -> tuple[int, int]:
    pending: dict[str, set[str]] = defaultdict(set)
    for path in sorted([*input_root.rglob("*.jsonl"), *input_root.rglob("*.json")]):
        if path.resolve() == output_path.resolve() or path.name == "bulk_review_manifest.json":
            continue
        if "license-report" in path.name:
            for row in _iter_json_values(path):
                if row.get("status") == "blocked" and row.get("record_id"):
                    pending[str(row["record_id"])].add("lexical")
            continue
        for row in _iter_json_values(path):
            scope = row.get("scope")
            if (
                row.get("status") == "needs-evidence"
                and scope in DECISION_SCOPES
                and row.get("record_id")
            ):
                pending[str(row["record_id"])].add(str(scope))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    decision_scope_count = 0
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record_id in sorted(pending):
            scopes = [scope for scope in SCOPE_ORDER if scope in pending[record_id]]
            decision_scope_count += sum(scope != "lexical" for scope in scopes)
            handle.write(
                json.dumps(
                    {
                        "record_id": record_id,
                        "needs_evidence_scopes": scopes,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )
    return len(pending), decision_scope_count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records, scopes = extract(args.input, args.output)
    print(json.dumps({"needs_evidence_records": records, "needs_evidence_scopes": scopes}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
