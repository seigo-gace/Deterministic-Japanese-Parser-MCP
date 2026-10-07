#!/usr/bin/env python3
"""Audit J-Ono source-authored adapter records before human review.

Hard failures are limited to objective corruption/integrity problems. Linguistic
ambiguity is reported for review and is never auto-resolved here.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import unicodedata

from tools.unified_semantic_data.source_adapter_contract import normalize_adapter_record

EXPECTED_RECORDS = 837


def _norm(value: str) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def _bad_text(value: str) -> bool:
    return "�" in value or any(
        unicodedata.category(ch) in {"Cc", "Cs"} and ord(ch) not in {9, 10, 13}
        for ch in value
    )


def audit_records(input_path: Path) -> tuple[dict, list[dict]]:
    rows: list[dict] = []
    issues: list[dict] = []
    exact_semantic: dict[str, list[str]] = defaultdict(list)
    surface_index: dict[str, list[dict]] = defaultdict(list)
    reading_present = 0
    pos_present = 0
    multi_meaning = 0

    for line_no, line in enumerate(Path(input_path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        raw = json.loads(line)
        if not isinstance(raw, dict):
            raise ValueError(f"J_ONO_ROW_NOT_OBJECT:{line_no}")
        record = normalize_adapter_record(raw, path=Path(input_path), line=line_no)
        rid = record["adapter_record_id"]
        if record["source_role"] != "lexical-definition":
            raise ValueError(f"J_ONO_ROLE_INVALID:{rid}")
        if record["source"].get("logical_source_id") != "j-ono-definitions":
            raise ValueError(f"J_ONO_SOURCE_INVALID:{rid}")

        core_texts = [
            *record["surfaces"],
            *record["readings"],
            *record["part_of_speech"],
            *record["meanings"],
        ]
        if any(_bad_text(text) for text in core_texts):
            raise ValueError(f"J_ONO_INVALID_UNICODE:{rid}")

        if record["readings"]:
            reading_present += 1
        else:
            issues.append({"record_id": rid, "kind": "MISSING_READING", "severity": "review"})
        if record["part_of_speech"]:
            pos_present += 1
        else:
            issues.append({"record_id": rid, "kind": "MISSING_POS", "severity": "review"})
        if len(record["meanings"]) > 1:
            multi_meaning += 1

        normalized_surfaces = [_norm(x) for x in record["surfaces"]]
        normalized_readings = [_norm(x) for x in record["readings"]]
        normalized_meanings = [_norm(x) for x in record["meanings"]]
        signature = json.dumps(
            {
                "surfaces": normalized_surfaces,
                "readings": normalized_readings,
                "pos": record["part_of_speech"],
                "meanings": normalized_meanings,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        exact_semantic[signature].append(rid)
        for surface in normalized_surfaces:
            surface_index[surface].append({
                "record_id": rid,
                "readings": normalized_readings,
                "meanings": normalized_meanings,
            })

        if any(m in normalized_surfaces for m in normalized_meanings):
            issues.append({"record_id": rid, "kind": "SELF_DEFINITION", "severity": "review"})
        if any(len(m) <= 1 for m in normalized_meanings):
            issues.append({"record_id": rid, "kind": "VERY_SHORT_MEANING", "severity": "review"})
        rows.append(record)

    if len(rows) != EXPECTED_RECORDS:
        raise ValueError(f"J_ONO_COUNT_MISMATCH:expected={EXPECTED_RECORDS}:actual={len(rows)}")

    exact_duplicate_groups = [
        ids for ids in exact_semantic.values() if len(ids) > 1
    ]
    for ids in exact_duplicate_groups:
        issues.append({
            "record_ids": ids,
            "kind": "EXACT_SEMANTIC_DUPLICATE",
            "severity": "review",
        })

    surface_collision_groups = 0
    for surface, members in surface_index.items():
        ids = {m["record_id"] for m in members}
        if len(ids) <= 1:
            continue
        surface_collision_groups += 1
        issues.append({
            "surface": surface,
            "record_ids": sorted(ids),
            "kind": "SURFACE_COLLISION",
            "severity": "review",
        })

    report = {
        "status": "J_ONO_DATA_QUALITY_AUDIT_COMPLETE",
        "record_count": len(rows),
        "unique_adapter_record_ids": len({r["adapter_record_id"] for r in rows}),
        "unique_surfaces": len(surface_index),
        "reading_coverage_records": reading_present,
        "reading_coverage_ratio": round(reading_present / len(rows), 6),
        "pos_coverage_records": pos_present,
        "pos_coverage_ratio": round(pos_present / len(rows), 6),
        "multi_meaning_records": multi_meaning,
        "exact_semantic_duplicate_groups": len(exact_duplicate_groups),
        "surface_collision_groups": surface_collision_groups,
        "review_issue_count": len(issues),
        "hard_failure_count": 0,
        "automatic_meaning_judgement": False,
        "automatic_approval": False,
        "runtime_promotion": False,
    }
    return report, issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--issues", type=Path, required=True)
    args = parser.parse_args()
    report, issues = audit_records(args.input)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with args.issues.open("w", encoding="utf-8", newline="\n") as handle:
        for issue in issues:
            handle.write(json.dumps(issue, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
