#!/usr/bin/env python3
"""Normalize Context v3 candidates into a checksum-fixed semantic collection.

This step makes the 5,000 checked-in candidate files reproducible inputs. It
preserves their review state and does not claim that constructed examples or
placeholder meanings are approved evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

import yaml

PLACEHOLDER_MARKERS = (
    "意味・機能はEvidence確認待ち",
    "意味・機能はevidence確認待ち",
    "Source確認待ち",
    "source確認待ち",
)


def normalize(value: Any) -> str:
    return str(value or "").strip()


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    return [value]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_strings(values: list[Any]) -> list[str]:
    return sorted({normalize(value) for value in values if normalize(value)})


def candidate_text(candidate: dict[str, Any]) -> str:
    return " ".join(
        normalize(candidate.get(key))
        for key in ("label", "meaning", "interpretation", "gloss")
    )


def normalize_candidate(
    candidate: Any,
    *,
    entry_id: str,
    index: int,
    evidence_id: str,
) -> tuple[dict[str, Any], bool]:
    if isinstance(candidate, str):
        item: dict[str, Any] = {"meaning": candidate}
    elif isinstance(candidate, dict):
        item = dict(candidate)
    else:
        item = {}
    text = candidate_text(item)
    placeholder = not text or any(marker in text for marker in PLACEHOLDER_MARKERS)
    item["candidate_id"] = normalize(
        item.get("candidate_id") or item.get("sense_id")
    ) or f"{entry_id}:context-sense:{index:03d}"
    item["review_status"] = "needs-evidence"
    item["evidence_ids"] = stable_strings(
        [*as_list(item.get("evidence_ids")), evidence_id]
    )
    item["candidate_kind"] = (
        "unresolved-shell" if placeholder else "source-derived-candidate"
    )
    item["meaning_promotion_allowed"] = False
    return item, placeholder


def build_collection(
    *,
    input_root: Path,
    output_root: Path,
    report_path: Path,
    expected_records: int,
) -> dict[str, Any]:
    manifest_path = input_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    collection_version = normalize(manifest.get("collection_version")) or "context-v3"
    paths = sorted(
        path
        for path in input_root.rglob("*.yaml")
        if path.name != "index.yaml"
    )
    if len(paths) != expected_records:
        raise ValueError(
            f"context record count mismatch: expected={expected_records} actual={len(paths)}"
        )
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    origin_counts: Counter[str] = Counter()
    license_counts: Counter[str] = Counter()
    source_candidate_count = 0
    unresolved_candidate_count = 0
    output_files: list[dict[str, Any]] = []

    for path in paths:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"context record must be an object: {path}")
        entry_id = normalize(raw.get("entry_id"))
        surface = normalize(raw.get("surface"))
        if not entry_id or not surface:
            raise ValueError(f"context entry_id/surface missing: {path}")
        provenance = dict(raw.get("provenance") or {})
        origin = normalize(provenance.get("origin")) or "context-v3"
        license_value = normalize(raw.get("license"))
        source_refs = stable_strings(as_list(raw.get("source")))
        record_sha = sha256_file(path)
        source_version = normalize(raw.get("source_version")) or collection_version
        evidence_id = f"context-record:{entry_id}:{record_sha[:16]}"

        meanings: list[dict[str, Any]] = []
        raw_meanings = as_list(raw.get("meaning_candidates"))
        if not raw_meanings:
            raw_meanings = [{}]
        for index, candidate in enumerate(raw_meanings, 1):
            normalized_candidate, placeholder = normalize_candidate(
                candidate,
                entry_id=entry_id,
                index=index,
                evidence_id=evidence_id,
            )
            meanings.append(normalized_candidate)
            if placeholder:
                unresolved_candidate_count += 1
            else:
                source_candidate_count += 1

        normalized = dict(raw)
        normalized.pop("domain", None)
        normalized["domains"] = stable_strings(
            [*as_list(raw.get("domains")), *as_list(raw.get("domain"))]
        )
        reading = normalize(raw.get("reading"))
        if reading:
            normalized["readings"] = stable_strings(
                [reading, *as_list(raw.get("readings"))]
            )
        source_pos = normalize(provenance.get("source_pos"))
        if source_pos:
            normalized["part_of_speech"] = stable_strings(
                [source_pos, *as_list(raw.get("part_of_speech"))]
            )
        normalized["meaning_candidates"] = meanings
        normalized["source_refs"] = source_refs
        normalized["source"] = {
            "dataset": origin,
            "version": source_version,
            "license": license_value,
            "source_id": entry_id,
            "source_url": next(
                (value for value in source_refs if value.startswith(("https://", "http://"))),
                "",
            ),
            "source_sha256": record_sha,
            "evidence_scope": "candidate_record",
            "attribution": origin,
        }
        normalized["review_status"] = "needs-evidence"
        normalized["approval_scopes"] = {
            "lexical": "approved",
            "semantic": "needs-evidence",
            "pragmatic": "needs-evidence",
            "task": "needs-evidence",
            "external_action": "needs-evidence",
        }
        normalized["review_metadata"] = {
            "candidate_record_evidence_id": evidence_id,
            "constructed_examples": bool(provenance.get("constructed_examples")),
            "meaning_promotion_allowed": False,
            "runtime_promotion_allowed": False,
            "source_refs": source_refs,
        }

        relative = path.relative_to(input_root)
        output_path = output_root / relative
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            yaml.safe_dump(
                normalized,
                allow_unicode=True,
                sort_keys=True,
                width=120,
            ),
            encoding="utf-8",
            newline="\n",
        )
        origin_counts[origin] += 1
        license_counts[license_value] += 1
        output_files.append({
            "path": str(relative),
            "sha256": sha256_file(output_path),
            "bytes": output_path.stat().st_size,
        })

    result = {
        "schema_version": "1.0.0",
        "mode": "review-only-context-semantic-collection",
        "source_collection_version": collection_version,
        "source_manifest_sha256": sha256_file(manifest_path),
        "record_count": len(paths),
        "source_derived_meaning_candidates": source_candidate_count,
        "unresolved_meaning_candidate_shells": unresolved_candidate_count,
        "origin_counts": dict(sorted(origin_counts.items())),
        "license_counts": dict(sorted(license_counts.items())),
        "automatic_approval": False,
        "automatic_runtime_promotion": False,
        "outputs": output_files,
    }
    (output_root / "manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--expected-records", type=int, default=5000)
    args = parser.parse_args()
    result = build_collection(
        input_root=args.input_root,
        output_root=args.output_root,
        report_path=args.report,
        expected_records=args.expected_records,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
