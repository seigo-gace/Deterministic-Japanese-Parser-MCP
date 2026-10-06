#!/usr/bin/env python3
"""Build Japanese-function projection metadata directly from Direct Final rows.

This is build-time only. It reuses the existing lane-assignment policy and the
published Direct Final manifest. It does not create lexical meaning, a second
runtime reader, or a new source authority.
"""
from __future__ import annotations

import argparse
from collections import Counter
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
    "morphology",
    "conjugation",
    "inflections",
    "semantic_targets",
    "usage_labels",
    "pragmatics",
    "syntax",
    "case",
    "clause",
    "document_structure",
    "discourse",
})


def _unique(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, (str, bytes)):
        values = [values]
    if not isinstance(values, (list, tuple, set)):
        values = [values]
    return sorted({str(value).strip() for value in values if str(value).strip()})


_TAG_TO_TARGETS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("onomatopoe", "mimetic", "擬音", "擬態"), "onomatopoeia"),
    (("multiword", "idiom", "compound", "fixed-expression", "fixed expression", "熟語", "慣用", "複合語"), "multiword"),
    (("syntax", "dependency", "predicate-argument", "係り受け", "構文"), "syntax"),
    (("case", "格関係"), "case"),
    (("clause", "節関係"), "clause"),
    (("document-structure", "document structure", "discourse-structure", "argumentation", "文書構造", "談話構造"), "document-structure"),
    (("usage", "context", "pragmatic", "register", "style", "用法", "文脈", "語用"), "usage"),
)

_SOURCE_DATASET_TARGETS: dict[str, set[str]] = {
    "onomatopoeia": {"j-ono-definitions", "public-onomatopoeia"},
}

_POS_TARGETS: dict[str, set[str]] = {
    "multiword": {"phrase", "句", "proverb", "contraction", "idiom", "multiword", "compound"},
    "document-structure": {"document", "文", "sentence", "paragraph"},
}



def _tag_texts(value: Any) -> list[str]:
    values: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            values.append(str(key))
            values.extend(_tag_texts(item))
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            values.extend(_tag_texts(item))
    elif value is not None:
        values.append(str(value))
    return _unique(values)


def _explicit_semantic_targets(row: dict[str, Any]) -> list[str]:
    targets = set(_unique(row.get("semantic_targets")))
    tag_values: list[str] = []
    for field in ("entry_types", "source_roles", "usage_labels", "syntax", "case", "clause", "document_structure", "discourse"):
        tag_values.extend(_tag_texts(row.get(field)))
    for relation in row.get("relations") or []:
        if isinstance(relation, dict):
            tag_values.extend(_tag_texts(relation.get("type")))
            tag_values.extend(_tag_texts(relation.get("relation_type")))
    normalized = " ".join(value.casefold().replace("_", "-") for value in tag_values)
    for markers, target in _TAG_TO_TARGETS:
        if any(marker.casefold().replace("_", "-") in normalized for marker in markers):
            targets.add(target)

    source_datasets = {value.casefold() for value in _unique(row.get("source_datasets"))}
    for target, source_ids in _SOURCE_DATASET_TARGETS.items():
        if source_datasets.intersection(source_ids):
            targets.add(target)

    pos_values = {value.casefold() for value in _unique(row.get("pos"))}
    for target, markers in _POS_TARGETS.items():
        if pos_values.intersection({marker.casefold() for marker in markers}):
            targets.add(target)

    if row.get("syntax") or row.get("case") or row.get("clause"):
        targets.add("syntax")
    if row.get("document_structure") or row.get("discourse"):
        targets.add("document-structure")
    return sorted(targets)


def _explicit_usage_labels(row: dict[str, Any]) -> list[str]:
    labels = set(_unique(row.get("usage_labels")))
    for value in _tag_texts(row.get("entry_types")) + _tag_texts(row.get("source_roles")):
        text = value.casefold()
        if any(marker in text for marker in ("usage", "context", "pragmatic", "register", "style", "用法", "文脈", "語用")):
            labels.add(value)
    return sorted(labels)


def _category_profile_values(row: dict[str, Any]) -> dict[str, list[str]]:
    relation_types: list[str] = []
    for relation in row.get("relations") or []:
        if isinstance(relation, dict):
            relation_types.extend(_tag_texts(relation.get("type")))
            relation_types.extend(_tag_texts(relation.get("relation_type")))
    sense_labels: list[str] = []
    for sense in row.get("senses") or []:
        if isinstance(sense, dict):
            sense_labels.extend(_tag_texts(sense.get("labels")))
    return {
        "pos": _unique(row.get("pos")),
        "entry_types": _unique(row.get("entry_types")),
        "source_datasets": _unique(row.get("source_datasets")),
        "source_roles": _unique(row.get("source_roles")),
        "relation_types": _unique(relation_types),
        "sense_labels": _unique(sense_labels),
        "semantic_targets": _explicit_semantic_targets(row),
        "usage_labels": _explicit_usage_labels(row),
    }


def _semantic_identity_sha(row: dict[str, Any]) -> str:
    identity = {
        "surface": str(row.get("surface") or "").strip(),
        "lemma": str(row.get("lemma") or row.get("surface") or "").strip(),
        "reading": str(row.get("reading") or "").strip(),
        "pos": _unique(row.get("pos")),
        "aliases": _unique(row.get("aliases")),
        "domains": _unique(row.get("domains")),
        "senses": row.get("senses") or [],
        "relations": row.get("relations") or [],
        "entry_types": _unique(row.get("entry_types")),
        "semantic_targets": _unique(row.get("semantic_targets")),
        "usage_labels": _unique(row.get("usage_labels")),
        "morphology": row.get("morphology") or {},
        "conjugation": row.get("conjugation") or {},
        "inflections": row.get("inflections") or [],
        "syntax": row.get("syntax") or {},
        "case": row.get("case") or {},
        "clause": row.get("clause") or {},
        "document_structure": row.get("document_structure") or {},
        "discourse": row.get("discourse") or {},
    }
    return projection._stable_json_sha256(identity)


def _projection_record(row: dict[str, Any], *, manifest_sha: str, version: str) -> dict[str, Any]:
    surface = str(row.get("surface") or "").strip()
    lemma = str(row.get("lemma") or surface).strip()
    reading = str(row.get("reading") or "").strip()
    aliases = _unique(row.get("aliases"))
    pos = _unique(row.get("pos"))
    senses = row.get("senses") or []
    examples = row.get("examples") or []
    relations = row.get("relations") or []
    semantic_targets = _explicit_semantic_targets(row)
    usage_labels = _explicit_usage_labels(row)
    morphology: dict[str, Any] = {}
    if isinstance(row.get("morphology"), dict):
        morphology.update(row.get("morphology") or {})
    if row.get("conjugation"):
        morphology["conjugation"] = row.get("conjugation")
    if row.get("inflections"):
        morphology["inflections"] = row.get("inflections")
    pragmatics = row.get("pragmatics") if isinstance(row.get("pragmatics"), dict) else {}
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
    if examples:
        auxiliary["example-evidence"] = examples

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
        "morphology": morphology,
        "domains": _unique(row.get("domains")),
        "senses": senses,
        "pragmatics": pragmatics,
        "semantic_facets": {
            "semantic_targets": semantic_targets,
            "usage_labels": usage_labels,
        },
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
    duplicate_count = 0
    unmapped_field_counts: Counter[str] = Counter()
    lane_counts = {lane: 0 for lane in projection.LANES}
    category_profiles = {
        name: Counter()
        for name in ("pos", "entry_types", "source_datasets", "source_roles", "relation_types", "sense_labels", "semantic_targets", "usage_labels")
    }
    version = str(source_manifest.get("date") or source_manifest.get("version") or "direct-final-runtime-v1")

    try:
        for row in _rows(parts):
            source_count += 1
            for profile_name, values in _category_profile_values(row).items():
                category_profiles[profile_name].update(values)
            for field_name in sorted(set(row) - _DIRECT_TO_PROJECTION_FIELDS):
                unmapped_field_counts[field_name] += 1
                unmapped_count += 1
            record_id = str(row["entry_id"])
            identity_sha = _semantic_identity_sha(row)
            existing = connection.execute(
                "SELECT canonical_record_id FROM record_identity WHERE identity_sha256=?",
                (identity_sha,),
            ).fetchone()
            if existing is not None:
                connection.execute(
                    "INSERT INTO duplicate_record(duplicate_record_id,canonical_record_id,identity_sha256) VALUES(?,?,?)",
                    (record_id, str(existing[0]), identity_sha),
                )
                duplicate_count += 1
                continue
            connection.execute(
                "INSERT INTO record_identity(identity_sha256,canonical_record_id) VALUES(?,?)",
                (identity_sha, record_id),
            )
            record = _projection_record(row, manifest_sha=manifest_sha, version=version)
            lanes = projection.assign_record_lanes(record)
            if not lanes:
                connection.execute(
                    "INSERT INTO rejected_record(record_id,reason) VALUES(?,?)",
                    (record_id, "no_supported_projection_lane"),
                )
                rejected_count += 1
            else:
                projected_count += 1
                connection.execute(
                    "INSERT INTO record_projection(record_id,lane_mask) VALUES(?,?)",
                    (record_id, projection.lane_mask_for(lanes)),
                )
                membership_count += len(lanes)
                for lane in lanes:
                    lane_counts[lane] += 1

        connection.executemany(
            "INSERT INTO unmapped_field_summary(field_name,record_count) VALUES(?,?)",
            sorted(unmapped_field_counts.items()),
        )
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
    if projected_count + rejected_count + duplicate_count != source_count:
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
        "duplicate_record_count": duplicate_count,
        "lanes": list(projection.LANES),
        "lane_counts": lane_counts,
        "source_category_profiles": {
            name: {
                "distinct_values": len(counter),
                "top_values": [
                    {"value": value, "records": count}
                    for value, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:500]
                ],
            }
            for name, counter in category_profiles.items()
        },
        "boundaries": {
            "canonical_dictionary_is_authority": False,
            "direct_final_manifest_is_source_authority": True,
            "meaning_generation": False,
            "unknown_field_preservation": True,
            "unknown_field_audit_mode": "field-count-summary",
            "source_payload_duplication": False,
            "rejected_record_preservation": True,
            "deterministic_lane_assignment": True,
            "semantic_identity_deduplication": True,
            "homograph_homophone_collapse": False,
            "storage_model": "single-record-lane-bitmask-v1",
            "build_identity_persisted": False,
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
