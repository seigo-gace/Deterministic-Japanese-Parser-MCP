#!/usr/bin/env python3
"""Validate deterministic compiled open-lexicon runtime assets."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_gzip_json(path: Path) -> Any:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def validate(root: Path, expected_records: int) -> dict[str, Any]:
    errors: list[str] = []
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if manifest.get("record_count") != expected_records:
        errors.append(
            f"record_count expected={expected_records} actual={manifest.get('record_count')}"
        )
    for flag in (
        "exact_lookup_only",
        "reading_alias_promotion",
        "semantic_auto_promotion",
        "intent_auto_promotion",
        "external_action_auto_promotion",
    ):
        expected = flag == "exact_lookup_only"
        if manifest.get(flag) is not expected:
            errors.append(f"{flag} must be {expected}")

    output_paths: set[str] = set()
    for item in manifest.get("outputs", []):
        relative = item.get("path")
        if not relative or relative in output_paths:
            errors.append(f"invalid or duplicate output path: {relative!r}")
            continue
        output_paths.add(relative)
        path = root / relative
        if not path.exists():
            errors.append(f"missing output: {relative}")
            continue
        if sha256_file(path) != item.get("sha256"):
            errors.append(f"sha256 mismatch: {relative}")
        if path.stat().st_size != item.get("bytes"):
            errors.append(f"byte-size mismatch: {relative}")

    required = {
        "indexes/canonical-groups.json.gz",
        "indexes/surface-index.json.gz",
        "indexes/reading-index.json.gz",
        "indexes/homograph-index.json.gz",
        "indexes/pos-index.json.gz",
        "indexes/domain-index.json.gz",
        "indexes/usage-index.json.gz",
        "indexes/record-locator.json.gz",
    }
    missing_required = required - output_paths
    if missing_required:
        errors.append(f"missing required indexes: {sorted(missing_required)}")

    canonical = load_gzip_json(root / "indexes/canonical-groups.json.gz")
    surfaces = load_gzip_json(root / "indexes/surface-index.json.gz")
    readings = load_gzip_json(root / "indexes/reading-index.json.gz")
    homographs = load_gzip_json(root / "indexes/homograph-index.json.gz")
    locator = load_gzip_json(root / "indexes/record-locator.json.gz")

    if len(locator) != expected_records:
        errors.append(
            f"record-locator size expected={expected_records} actual={len(locator)}"
        )
    if len(canonical) != manifest.get("unique_lemmas"):
        errors.append("unique_lemmas mismatch")
    if len(surfaces) != manifest.get("unique_surfaces"):
        errors.append("unique_surfaces mismatch")
    if len(readings) != manifest.get("unique_readings"):
        errors.append("unique_readings mismatch")

    expected_homographs = {
        surface: owners for surface, owners in surfaces.items() if len(owners) > 1
    }
    if homographs != expected_homographs:
        errors.append("homograph index is not the exact ambiguous-surface subset")

    all_ids = set(locator)
    surface_keys = set(surfaces)
    for surface, owners in surfaces.items():
        if not surface or owners != sorted(set(owners)):
            errors.append(f"invalid surface owner list: {surface!r}")
            break
        unknown = set(owners) - all_ids
        if unknown:
            errors.append(f"surface index has unknown record IDs: {surface!r}")
            break
    for reading, mappings in readings.items():
        if not reading:
            errors.append("empty reading key")
            break
        for mapping in mappings:
            if mapping.get("record_id") not in all_ids:
                errors.append(f"reading index has unknown record ID: {reading!r}")
                break

    # Canonical groups are orthographic-only. Every member must exist in the
    # surface index. Readings are intentionally not added here by the compiler.
    for lemma, members in canonical.items():
        if lemma not in members:
            errors.append(f"canonical group missing lemma: {lemma!r}")
            break
        if members != sorted(set(members)):
            errors.append(f"canonical group is not deterministic: {lemma!r}")
            break
        unknown = set(members) - surface_keys
        if unknown:
            errors.append(f"canonical group has non-surface aliases: {lemma!r}")
            break

    report = {
        "status": "PASS" if not errors else "FAIL",
        "record_count": manifest.get("record_count"),
        "unique_lemmas": len(canonical),
        "unique_surfaces": len(surfaces),
        "unique_readings": len(readings),
        "homograph_surfaces": len(homographs),
        "output_files": len(output_paths),
        "errors": errors,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--expected-records", type=int, default=120000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = validate(args.root, args.expected_records)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
