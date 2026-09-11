#!/usr/bin/env python3
"""Validate GitHub-managed source-authored meaning data release assets.

This contract is intentionally not a Direct Final runtime promotion gate. It
verifies that the reusable meaning-data bundle is present, internally consistent,
and still bounded as source-authored data that requires an explicit later runtime
promotion decision.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile
from typing import Any, Callable

MEANING_ASSET = "mcp-source-authored-meaning-factory-v1.zip"
ROLE_PREFIX = "mcp-auxiliary-source-role-shard-"
RAW_INPUT_PARTS = [
    "mcp-collected-raw-factory-input-v1.zip.part-00",
    "mcp-collected-raw-factory-input-v1.zip.part-01",
    "mcp-collected-raw-factory-input-v1.zip.part-02",
]
SEMANTIC_MEMBER = "meaning-factory/adapter-output/semantic-reference.jsonl"
LEXICAL_MEMBER = "meaning-factory/adapter-output/lexical-candidates.jsonl"
EVIDENCE_MEMBER = "meaning-factory/adapter-output/canonical-evidence.jsonl"
ADAPTER_MANIFEST_MEMBER = "meaning-factory/adapter-output/manifest.json"
FACTORY_REPORT_MEMBER = "meaning-factory/meaning-factory-report.json"
SOURCE_RECORDS_MEMBER = "meaning-factory/source-adapter-records.jsonl"
UNRESOLVED_MEMBER = "meaning-factory/unresolved-meaning-records.jsonl"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_member(zf: zipfile.ZipFile, name: str) -> dict[str, Any]:
    with zf.open(name) as raw:
        return json.loads(raw.read().decode("utf-8"))


def _member_sha256(zf: zipfile.ZipFile, name: str) -> str:
    digest = hashlib.sha256()
    with zf.open(name) as raw:
        for block in iter(lambda: raw.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _scan_jsonl_member(
    zf: zipfile.ZipFile,
    name: str,
    validator: Callable[[dict[str, Any], int], None] | None = None,
) -> int:
    count = 0
    with zf.open(name) as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8")
        for line_number, line in enumerate(text, 1):
            if not line.strip():
                continue
            count += 1
            if validator is not None:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"{name}:{line_number}: row must be an object")
                validator(value, line_number)
    return count


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _validate_semantic(row: dict[str, Any], line_number: int) -> None:
    prefix = f"{SEMANTIC_MEMBER}:{line_number}"
    _require(row.get("meaning_origin") == "source-authored", f"{prefix}: meaning_origin must be source-authored")
    _require(bool(row.get("meanings")), f"{prefix}: meanings must be non-empty")
    _require(bool(row.get("surface") or row.get("surfaces")), f"{prefix}: surface/surfaces required")
    source = row.get("source") or {}
    _require(isinstance(source, dict), f"{prefix}: source must be an object")
    for key in ("source_id", "logical_source_id", "license", "source_record_sha256"):
        _require(bool(source.get(key)), f"{prefix}: source.{key} required")


def _validate_lexical(row: dict[str, Any], line_number: int) -> None:
    prefix = f"{LEXICAL_MEMBER}:{line_number}"
    _require(row.get("automatic_runtime_promotion") is False, f"{prefix}: automatic runtime promotion must stay false")
    _require(bool(row.get("meaning_candidates")), f"{prefix}: meaning_candidates must be non-empty")
    _require(bool(row.get("record_id")), f"{prefix}: record_id required")
    _require(bool(row.get("surfaces")), f"{prefix}: surfaces required")


def _validate_source(row: dict[str, Any], line_number: int) -> None:
    prefix = f"{SOURCE_RECORDS_MEMBER}:{line_number}"
    _require(row.get("source_role") == "lexical-definition", f"{prefix}: source_role must be lexical-definition")
    _require(bool(row.get("meanings")), f"{prefix}: meanings must be non-empty")
    _require(bool(row.get("surfaces")), f"{prefix}: surfaces required")


def _sha256_joined(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def validate(
    asset_root: Path,
    *,
    require_role_shards: bool = False,
    require_raw_factory_input: bool = False,
    expected_raw_factory_input_sha256: str | None = None,
    deep_scan: bool = True,
) -> dict[str, Any]:
    meaning_zip = asset_root / MEANING_ASSET
    if not meaning_zip.is_file():
        raise FileNotFoundError(meaning_zip)

    assets: dict[str, Any] = {}
    for path in sorted(asset_root.glob("*.zip")):
        with zipfile.ZipFile(path) as zf:
            bad_member = zf.testzip()
            if bad_member is not None:
                raise ValueError(f"corrupt zip member in {path.name}: {bad_member}")
            members = zf.namelist()
            assets[path.name] = {
                "bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
                "member_count": len(members),
                "uncompressed_bytes": sum(info.file_size for info in zf.infolist()),
            }

    role_assets = sorted(name for name in assets if name.startswith(ROLE_PREFIX))
    if require_role_shards:
        _require(role_assets == ["mcp-auxiliary-source-role-shard-0-v1.zip", "mcp-auxiliary-source-role-shard-1-v1.zip"], "expected role shard 0 and 1 assets")

    raw_input_parts = [asset_root / name for name in RAW_INPUT_PARTS if (asset_root / name).is_file()]
    raw_input_sha256 = None
    if require_raw_factory_input:
        missing_raw = [name for name in RAW_INPUT_PARTS if not (asset_root / name).is_file()]
        _require(not missing_raw, "missing raw factory input parts: " + ", ".join(missing_raw))
        raw_input_sha256 = _sha256_joined([asset_root / name for name in RAW_INPUT_PARTS])
        if expected_raw_factory_input_sha256:
            _require(
                raw_input_sha256 == expected_raw_factory_input_sha256,
                "raw factory input reconstructed sha256 mismatch",
            )

    with zipfile.ZipFile(meaning_zip) as zf:
        required_members = [
            ADAPTER_MANIFEST_MEMBER,
            FACTORY_REPORT_MEMBER,
            SEMANTIC_MEMBER,
            LEXICAL_MEMBER,
            EVIDENCE_MEMBER,
            SOURCE_RECORDS_MEMBER,
            UNRESOLVED_MEMBER,
        ]
        missing = [name for name in required_members if name not in zf.namelist()]
        if missing:
            raise FileNotFoundError("missing meaning members: " + ", ".join(missing))

        manifest = _json_member(zf, ADAPTER_MANIFEST_MEMBER)
        report = _json_member(zf, FACTORY_REPORT_MEMBER)
        _require(manifest.get("mode") == "mcp-universal-source-adapter-contract", "adapter manifest mode mismatch")
        _require(report.get("mode") == "frozen-raw-source-authored-meaning-factory", "factory report mode mismatch")
        _require((manifest.get("boundaries") or {}).get("runtime_promotion") is False, "runtime promotion must remain false in source data")
        _require((report.get("boundaries") or {}).get("automatic_runtime_promotion") is False, "automatic runtime promotion must remain false")
        _require((report.get("boundaries") or {}).get("source_authored_meanings_only") is True, "source-authored-only boundary required")
        _require(int(manifest.get("semantic_reference_record_count") or 0) > 0, "semantic reference records required")

        outputs = manifest.get("outputs") or {}
        for member, output_name in (
            (SEMANTIC_MEMBER, "semantic-reference.jsonl"),
            (LEXICAL_MEMBER, "lexical-candidates.jsonl"),
            (EVIDENCE_MEMBER, "canonical-evidence.jsonl"),
        ):
            expected = (outputs.get(output_name) or {}).get("sha256")
            _require(bool(expected), f"manifest output sha256 missing for {output_name}")
            actual = _member_sha256(zf, member)
            _require(actual == expected, f"sha256 mismatch for {output_name}")

        source_meta = (report.get("files") or {}).get("source_adapter_records") or {}
        _require(_member_sha256(zf, SOURCE_RECORDS_MEMBER) == source_meta.get("sha256"), "source adapter records sha256 mismatch")
        unresolved_meta = (report.get("files") or {}).get("unresolved") or {}
        _require(_member_sha256(zf, UNRESOLVED_MEMBER) == unresolved_meta.get("sha256"), "unresolved records sha256 mismatch")

        def declared_int(value: Any) -> int:
            if value is None:
                return -1
            return int(value)

        counts: dict[str, int] = {}
        if deep_scan:
            counts["semantic_reference_records"] = _scan_jsonl_member(zf, SEMANTIC_MEMBER, _validate_semantic)
            counts["lexical_candidate_records"] = _scan_jsonl_member(zf, LEXICAL_MEMBER, _validate_lexical)
            counts["source_adapter_records"] = _scan_jsonl_member(zf, SOURCE_RECORDS_MEMBER, _validate_source)
            counts["unresolved_records"] = _scan_jsonl_member(zf, UNRESOLVED_MEMBER)
            counts["canonical_evidence_records"] = _scan_jsonl_member(zf, EVIDENCE_MEMBER)
            _require(counts["semantic_reference_records"] == declared_int(manifest.get("semantic_reference_record_count")), "semantic reference count mismatch")
            _require(counts["lexical_candidate_records"] == declared_int(manifest.get("lexical_candidate_record_count")), "lexical candidate count mismatch")
            _require(counts["source_adapter_records"] == declared_int(report.get("adapter_record_count")), "source adapter count mismatch")
            _require(counts["unresolved_records"] == declared_int(report.get("unresolved_record_count")), "unresolved count mismatch")
            _require(counts["canonical_evidence_records"] == declared_int(manifest.get("canonical_evidence_record_count")), "canonical evidence count mismatch")
        else:
            counts = {
                "semantic_reference_records": int(manifest.get("semantic_reference_record_count") or 0),
                "lexical_candidate_records": int(manifest.get("lexical_candidate_record_count") or 0),
                "source_adapter_records": int(report.get("adapter_record_count") or 0),
                "unresolved_records": int(report.get("unresolved_record_count") or 0),
                "canonical_evidence_records": int(manifest.get("canonical_evidence_record_count") or 0),
            }

    return {
        "schema_version": "djpmcp.source-authored-meaning-release-contract.v1",
        "status": "pass",
        "asset_root": str(asset_root),
        "assets": assets,
        "meaning_asset": MEANING_ASSET,
        "role_assets": role_assets,
        "raw_factory_input_parts": [path.name for path in raw_input_parts],
        "raw_factory_input_reconstructed_sha256": raw_input_sha256,
        "counts": counts,
        "usable_as": "github-managed-source-authored-meaning-data",
        "direct_final_runtime_ready": False,
        "runtime_promotion_required": True,
        "boundaries": {
            "drive_source_of_truth": False,
            "notion_source_of_truth": False,
            "automatic_runtime_promotion": False,
            "direct_final_claimed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-role-shards", action="store_true")
    parser.add_argument("--require-raw-factory-input", action="store_true")
    parser.add_argument("--expected-raw-factory-input-sha256")
    parser.add_argument("--shallow", action="store_true", help="verify manifests/checksums without scanning every JSONL row")
    args = parser.parse_args()
    report = validate(
        args.asset_root,
        require_role_shards=args.require_role_shards,
        require_raw_factory_input=args.require_raw_factory_input,
        expected_raw_factory_input_sha256=args.expected_raw_factory_input_sha256,
        deep_scan=not args.shallow,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
