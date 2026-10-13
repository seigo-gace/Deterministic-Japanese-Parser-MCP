#!/usr/bin/env python3
"""Read-only, deterministic inventory of declared source roles and unresolved placement evidence.

This is a starting inventory, NOT an assertion that fields are mapped or consumed at runtime.
"""
import argparse
import csv
import json
from pathlib import Path

COLUMNS = (
    "source_id", "artifact_name", "source_role", "parser_family",
    "rights_lane", "public_runtime_eligible", "field_path",
    "field_semantics", "japanese_reading_need", "processing_stage",
    "logical_destination", "input_records", "canonical_records",
    "assigned_records", "retrievable_records", "consumed_records",
    "gap_status", "evidence",
)


def inventory(profile):
    sources = profile["sources"]
    if not isinstance(sources, list):
        raise ValueError("sources must be an array")
    unique = set()
    rows = []
    for source in sources:
        identity = source["source_id"]
        if identity in unique:
            raise ValueError(f"duplicate source_id: {identity}")
        unique.add(identity)
        roles = source.get("source_roles") or ["UNKNOWN"]
        if not isinstance(roles, list) or not all(isinstance(r, str) and r for r in roles):
            raise ValueError(f"invalid source_roles: {identity}")
        for role in sorted(set(roles)):
            # Field semantics and runtime consumption are NOT derivable from role labels.
            row = {key: "UNKNOWN" for key in COLUMNS}
            row.update(
                source_id=identity,
                artifact_name=source.get("artifact_name", "UNKNOWN"),
                source_role=role,
                parser_family=source.get("parser_family", "UNKNOWN"),
                rights_lane=source.get("rights_lane", "UNKNOWN"),
                public_runtime_eligible=str(source.get("public_runtime_eligible", "UNKNOWN")).lower(),
                gap_status="NEEDS_FIELD_AND_RUNTIME_EVIDENCE",
                evidence="config/source_payload_profiles.json",
            )
            rows.append(row)
    return sorted(rows, key=lambda row: (row["source_id"], row["source_role"]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", type=Path, default=Path("config/source_payload_profiles.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.profiles.read_text(encoding="utf-8"))
    rows = inventory(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({
        "declared_source_count": len({row["source_id"] for row in rows}),
        "source_role_rows": len(rows),
        "field_coverage_verified": False,
        "runtime_consumption_verified": False,
        "output": str(args.output),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
