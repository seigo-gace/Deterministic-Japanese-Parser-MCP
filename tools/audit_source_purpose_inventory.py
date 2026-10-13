#!/usr/bin/env python3
"""Read-only, deterministic inventory of declared source roles and unresolved placement evidence.

This is a starting inventory, NOT an assertion that fields are mapped or consumed at runtime.
"""
import argparse
import csv
import json
from collections import Counter
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


def observed_fields(records_path):
    """Count actual JSONL field paths/types without asserting semantics or destination."""
    counts = Counter()
    records = 0

    def walk(value, prefix):
        if isinstance(value, dict):
            for key, child in sorted(value.items()):
                child_path = f"{prefix}.{key}" if prefix else key
                counts[(child_path, type(child).__name__)] += 1
                walk(child, child_path)
        elif isinstance(value, list):
            # Array item shape is counted under the same deterministic [] path.
            for child in value:
                walk(child, f"{prefix}[]")

    with records_path.open(encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at line {line_no}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"non-object record at line {line_no}")
            records += 1
            walk(record, "")
    return records, [
        {"field_path": path, "value_type": kind, "observed_occurrences": count,
         "information_kind": "UNCLASSIFIED_REQUIRES_SOURCE_EVIDENCE",
         "logical_destination": "UNDECIDED"}
        for (path, kind), count in sorted(counts.items())
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", type=Path, default=Path("config/source_payload_profiles.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--records", type=Path, help="Optional actual adapter/canonical JSONL for observed Field inventory")
    parser.add_argument("--fields-output", type=Path, help="JSON field inventory output, required with --records")
    args = parser.parse_args()
    if bool(args.records) != bool(args.fields_output):
        parser.error("--records and --fields-output must be supplied together")
    data = json.loads(args.profiles.read_text(encoding="utf-8"))
    rows = inventory(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    observed_count = None
    if args.records:
        observed_count, fields = observed_fields(args.records)
        args.fields_output.parent.mkdir(parents=True, exist_ok=True)
        args.fields_output.write_text(json.dumps(fields, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "declared_source_count": len({row["source_id"] for row in rows}),
        "source_role_rows": len(rows),
        "field_coverage_verified": False,
        "observed_input_records": observed_count,
        "observed_field_types": len(fields) if args.records else None,
        "runtime_consumption_verified": False,
        "output": str(args.output),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
