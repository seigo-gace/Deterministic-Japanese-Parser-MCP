#!/usr/bin/env python3
"""Build Japanese-function projection metadata directly from Direct Final rows.

This is build-time only. It reuses the existing lane-assignment policy and the
published Direct Final manifest. It does not create lexical meaning, a second
runtime reader, or a new source authority.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from tools.compile_direct_final_runtime import _rows, _validate
from tools.unified_semantic_data import japanese_function_projection as projection


_DIRECT_TO_PROJECTION_FIELDS = frozenset({
    "entry_id",
    "surface",
    "lemma",
    "reading",
    "pos",
    "aliases",
    "domains",
    "senses",
    "examples",
    "relations",
    "source_datasets",
    "source_roles",
    "rights_lanes",
    "evidence_samples",
    "entry_types",
})


def _unique(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, (str, bytes)):
        values = [values]
    if not isinstance(values, (list, tuple, set)):
        values = [values]
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _projection_record(row: dict[str, Any], *, manifest_sha: str, version: str) -> dict[str, Any]:
    surface = str(row.get("surface") or "").strip()
    lemma = str(row.get("lemma") or surface).strip()
    reading = str(row.get("reading") or "").strip()
    aliases = _unique(row.get("aliases"))
    pos = _unique(row.get("pos"))
    senses = row.get("senses") or []
    examples = row.get("examples") or []
    relations = row.get("relations") or []
    source_datasets = _unique(row.get("source_datasets"))
    source_roles = _unique(row.get("source_roles"))
    rights_lanes = _unique(row.get("rights_lanes"))
    evidence_samples = _unique(row.get("evidence_samples"))
    entry_types = _unique(row.get("entry_types"))

    auxiliary: dict[str, Any] = {}
    if relations:
        auxiliary["lexical-relation"] = relations
    if entry_types:
        auxiliary["direct-final-entry-types"] = entry_types
    if source_roles:
        auxiliary["source-roles"] = source_roles
    if rights_lanes:
        auxiliary["rights-lanes"] = rights_lanes

    source_dataset_text = ",".join(source_datasets)
    source_records = [
        {
            "source_record_id": value,
            "source_dataset": source_dataset_text,
        }
        for value in evidence_samples
    ]
    if not source_records:
        source_records = [
            {
                "source_record_id": str(row["entry_id"]),
                "source_dataset": source_dataset_text,
            }
        ]

    return {
        "dictionary_id": str(row["entry_id"]),
        "lemma": lemma,
        "surfaces": _unique([surface, lemma, *aliases]),
        "normalized_surfaces": [],
        "readings": [reading] if reading else [],
        "reading_mappings": (
            [{"reading": reading, "restricted_to": [], "no_kanji": False}]
            if reading
            else []
        ),
        "part_of_speech": pos,
        "morphology": {},
        "domains": _unique(row.get("domains")),
        "senses": senses,
        "pragmatics": {"examples": examples} if examples else {},
        "semantic_facets": {"usage_labels": entry_types} if entry_types else {},
        "auxiliary_evidence": auxiliary,
        "source_records": source_records,
        "source": {
            "dataset": "MCP Direct Final Runtime",
            "version": version,
            "source_id": str(row["entry_id"]),
            "source_sha256": manifest_sha,
            "source_datasets": source_datasets,
            "source_roles": source_roles,
            "rights_lanes": rights_lanes,
            "evidence_samples": evidence_samples,
        },
    }


def compile_direct_final_projection(
    *,
    manifest_path: Path,
    input_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    manifest_path = Path(manifest_path)
    input_root = Path(input_root)
    output_root = Path(output_root)
    source_manifest, parts, _support = _validate(manifest_path, input_root)
    manifest_sha = projection._sha256_file(manifest_path)
    expected = int((source_manifest.get("validation") or {}).get("full_json_records_validated", 0))
    if expected <= 0:
        expected = sum(int(item.get("records", 0)) for item in source_manifest.get("parts") or [])
    if expected <= 0:
        raise ValueError("Direct Final manifest does not declare a positive record count")

    staging = output_root.with_name(output_root.name + ".staging")
    backup = output_root.with_name(output_root.name + ".rollback")
    for path in (staging, backup):
        if path.exists():
            shutil.rmtree(path)
    staging.mkdir(parents=True)
    database_path = staging / "projection.sqlite3"
    connection = projection._connect(database_path)

    source_count = 0
    projected_count = 0
    rejected_count = 0
    membership_count = 0
    unmapped_count = 0
    lane_counts = {lane: 0 for lane in projection.LANES}
    version = str(source_manifest.get("date") or source_manifest.get("version") or "direct-final-runtime-v1")

    try:
        for row in _rows(parts):
            source_count += 1
            record = _projection_record(row, manifest_sha=manifest_sha, version=version)
            record_id = record["dictionary_id"]
            lanes = projection.assign_record_lanes(record)
            if not lanes:
                connection.execute(
                    "INSERT INTO rejected_record(record_id,reason,payload_json) VALUES(?,?,?)",
                    (record_id, "no_supported_projection_lane", json.dumps(row, ensure_ascii=False, sort_keys=True)),
                )
                rejected_count += 1
            else:
                projected_count += 1
                for lane, reasons in lanes.items():
                    connection.execute(
                        "INSERT INTO record_lane(record_id,lane,reasons_json) VALUES(?,?,?)",
                        (record_id, lane, json.dumps(reasons, ensure_ascii=False, sort_keys=True)),
                    )
                    membership_count += 1
                    lane_counts[lane] += 1

            for field_name in sorted(set(row) - _DIRECT_TO_PROJECTION_FIELDS):
                connection.execute(
                    "INSERT INTO unmapped_field(record_id,field_name,payload_json,reason) VALUES(?,?,?,?)",
                    (
                        record_id,
                        field_name,
                        json.dumps(row[field_name], ensure_ascii=False, sort_keys=True),
                        "direct_final_field_not_consumed_by_projection_adapter_v1",
                    ),
                )
                unmapped_count += 1

        connection.executemany(
            "INSERT INTO bundle_metadata(key,value) VALUES(?,?)",
            sorted(
                {
                    "schema_version": projection.PROJECTION_SCHEMA_VERSION,
                    "projection_policy_version": projection.PROJECTION_POLICY_VERSION,
                    "scoring_policy_version": projection.SCORING_POLICY_VERSION,
                    "canonical_manifest_sha": manifest_sha,
                    "source_kind": "direct-final-runtime-v1",
                }.items()
            ),
        )
        connection.commit()
        connection.execute("VACUUM")
    finally:
        connection.close()

    if source_count != expected:
        raise ValueError(f"Direct Final source count mismatch: manifest={expected} observed={source_count}")
    if projected_count + rejected_count != source_count:
        raise ValueError("Direct Final projection conservation mismatch")

    output_manifest = {
        "schema_version": projection.PROJECTION_SCHEMA_VERSION,
        "projection_policy_version": projection.PROJECTION_POLICY_VERSION,
        "scoring_policy_version": projection.SCORING_POLICY_VERSION,
        "canonical_manifest_sha": manifest_sha,
        "canonical_record_count": expected,
        "observed_canonical_record_count": source_count,
        "projected_record_count": projected_count,
        "rejected_record_count": rejected_count,
        "lane_membership_count": membership_count,
        "unmapped_field_count": unmapped_count,
        "lanes": list(projection.LANES),
        "lane_counts": lane_counts,
        "boundaries": {
            "canonical_dictionary_is_authority": False,
            "direct_final_manifest_is_source_authority": True,
            "meaning_generation": False,
            "unknown_field_preservation": True,
            "rejected_record_preservation": True,
            "deterministic_lane_assignment": True,
            "full_source_conservation_required": True,
        },
        "source": {
            "kind": "direct-final-runtime-v1",
            "manifest_sha256": manifest_sha,
            "expected_records": expected,
        },
        "outputs": {
            "projection.sqlite3": {
                "sha256": projection._sha256_file(database_path),
                "bytes": database_path.stat().st_size,
            }
        },
    }
    (staging / "manifest.json").write_text(
        json.dumps(output_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    projection.validate_projection_bundle(staging)

    moved_old = False
    try:
        if output_root.exists():
            os.replace(output_root, backup)
            moved_old = True
        os.replace(staging, output_root)
    except Exception:
        if moved_old and backup.exists() and not output_root.exists():
            os.replace(backup, output_root)
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup)
    return projection.validate_projection_bundle(output_root)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    result = compile_direct_final_projection(
        manifest_path=args.manifest,
        input_root=args.input_root,
        output_root=args.output_root,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
