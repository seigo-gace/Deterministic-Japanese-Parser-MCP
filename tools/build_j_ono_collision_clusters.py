#!/usr/bin/env python3
"""Build deterministic machine-first J-Ono polysemy/variant review clusters.

This tool groups raw divergent surface-collision issues by the exact record-id set.
It never merges senses, rewrites meanings, approves records, or promotes runtime data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from unified_semantic_data.source_adapter_contract import normalize_adapter_record
except ModuleNotFoundError:
    from tools.unified_semantic_data.source_adapter_contract import normalize_adapter_record

EXPECTED_RECORDS = 837
EXPECTED_CLUSTERS = 129


def _stable_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        value = str(value or "").strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _cluster_id(record_ids: list[str]) -> str:
    payload = "\n".join(sorted(record_ids)).encode("utf-8")
    return "j-ono-cluster-" + hashlib.sha256(payload).hexdigest()[:20]


def load_records(path: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for line_no, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        raw = json.loads(line)
        row = normalize_adapter_record(raw, path=Path(path), line=line_no)
        rid = row["adapter_record_id"]
        if rid in rows:
            raise ValueError(f"J_ONO_CLUSTER_DUPLICATE_RECORD_ID:{rid}")
        if row["source"].get("logical_source_id") != "j-ono-definitions":
            raise ValueError(f"J_ONO_CLUSTER_SOURCE_INVALID:{rid}")
        rows[rid] = row
    if len(rows) != EXPECTED_RECORDS:
        raise ValueError(f"J_ONO_CLUSTER_RECORD_COUNT_MISMATCH:{len(rows)}")
    return rows


def build_clusters(records_path: Path, issues_path: Path) -> tuple[dict, list[dict]]:
    records = load_records(records_path)
    grouped: dict[tuple[str, ...], set[str]] = {}

    for line_no, line in enumerate(Path(issues_path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        issue = json.loads(line)
        kind = str(issue.get("kind") or "")
        if kind not in {
            "SURFACE_COLLISION_DIVERGENT_MEANING",
            "SURFACE_COLLISION_SAME_MEANING",
        }:
            continue
        record_ids = tuple(sorted(str(x) for x in issue.get("record_ids") or []))
        if len(record_ids) < 2:
            raise ValueError(f"J_ONO_CLUSTER_INVALID_RECORD_SET:{line_no}")
        missing = [rid for rid in record_ids if rid not in records]
        if missing:
            raise ValueError(f"J_ONO_CLUSTER_UNKNOWN_RECORD:{missing[0]}")
        surface = str(issue.get("surface") or "").strip()
        if not surface:
            raise ValueError(f"J_ONO_CLUSTER_EMPTY_SURFACE:{line_no}")
        grouped.setdefault(record_ids, set()).add(surface)

    clusters: list[dict] = []
    for record_ids, shared_surfaces in sorted(grouped.items()):
        members = [records[rid] for rid in record_ids]
        meaning_signatures = {
            json.dumps(member["meanings"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            for member in members
        }
        collision_type = "divergent_meaning" if len(meaning_signatures) > 1 else "same_meaning"
        cluster = {
            "cluster_id": _cluster_id(list(record_ids)),
            "cluster_type": collision_type,
            "review_required": True,
            "automatic_merge": False,
            "automatic_meaning_judgement": False,
            "runtime_promotion": False,
            "record_ids": list(record_ids),
            "shared_variant_surfaces": sorted(shared_surfaces),
            "record_count": len(record_ids),
            "variant_surface_count": len(shared_surfaces),
            "members": [],
        }
        for member in members:
            source = member.get("source") or {}
            cluster["members"].append({
                "record_id": member["adapter_record_id"],
                "surfaces": _stable_unique(member["surfaces"]),
                "readings": _stable_unique(member["readings"]),
                "part_of_speech": _stable_unique(member["part_of_speech"]),
                "meanings": _stable_unique(member["meanings"]),
                "source_record_id": str(source.get("source_record_id") or ""),
                "logical_source_id": str(source.get("logical_source_id") or ""),
            })
        clusters.append(cluster)

    report = {
        "status": "J_ONO_COLLISION_CLUSTER_BUILD_COMPLETE",
        "record_count": len(records),
        "cluster_count": len(clusters),
        "divergent_meaning_cluster_count": sum(c["cluster_type"] == "divergent_meaning" for c in clusters),
        "same_meaning_cluster_count": sum(c["cluster_type"] == "same_meaning" for c in clusters),
        "max_record_count": max((c["record_count"] for c in clusters), default=0),
        "max_variant_surface_count": max((c["variant_surface_count"] for c in clusters), default=0),
        "automatic_merge": False,
        "automatic_meaning_judgement": False,
        "runtime_promotion": False,
    }
    if report["cluster_count"] != EXPECTED_CLUSTERS:
        raise ValueError(
            f"J_ONO_CLUSTER_COUNT_MISMATCH:expected={EXPECTED_CLUSTERS}:actual={report['cluster_count']}"
        )
    return report, clusters


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--issues", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report, clusters = build_clusters(args.records, args.issues)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for cluster in clusters:
            handle.write(json.dumps(cluster, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
