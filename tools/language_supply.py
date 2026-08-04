#!/usr/bin/env python3
"""Convert collected language evidence into review-only proposals."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dictionary_supply.proposals import PROPOSAL_SCHEMA_VERSION

_BLOCKED_LICENSE_MARKERS = {"PRIVATE", "UNKNOWN", "UNLICENSED"}
_ALLOWED_EVIDENCE_SCOPES = {"runtime_data", "verification_only"}
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


def _load(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".jsonl":
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if isinstance(value, list):
        return list(value)
    if not isinstance(value, dict):
        raise ValueError(f"unsupported collected data root: {path}")
    entries = value.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError(f"entries must be a list: {path}")
    return list(entries)


def _validate_evidence(entry_id: str, evidence: list[dict[str, Any]]) -> None:
    if not evidence:
        raise ValueError(f"evidence is required: {entry_id}")
    for item in evidence:
        for key in ("dataset", "version", "license", "source_id"):
            if not item.get(key):
                raise ValueError(f"evidence.{key} is required: {entry_id}")
        license_value = str(item["license"]).upper()
        if any(marker in license_value for marker in _BLOCKED_LICENSE_MARKERS):
            raise ValueError(
                f"blocked evidence license: {entry_id}: {item['license']}"
            )
        scope = item.get("evidence_scope")
        if scope not in _ALLOWED_EVIDENCE_SCOPES:
            raise ValueError(
                f"evidence_scope must be runtime_data or verification_only: "
                f"{entry_id}"
            )
        if item.get("dataset") != "project-authored semantic contract":
            if not item.get("source_url"):
                raise ValueError(f"evidence.source_url is required: {entry_id}")
            digest = str(item.get("source_sha256", ""))
            if not _SHA256.fullmatch(digest):
                raise ValueError(
                    f"evidence.source_sha256 must be 64 hex characters: "
                    f"{entry_id}"
                )


def _proposal(entry: dict[str, Any], source_path: Path) -> dict[str, Any]:
    entry_id = entry.get("entry_id")
    if not entry_id:
        raise ValueError(f"entry_id is required: {source_path}")
    evidence = entry.get("evidence", [])
    _validate_evidence(entry_id, evidence)
    payload = {
        key: value
        for key, value in entry.items()
        if key not in {"review_status"}
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    return {
        "schema_version": PROPOSAL_SCHEMA_VERSION,
        "proposal_id": (
            "PROP-LANGUAGE-"
            + hashlib.sha256(encoded).hexdigest()[:20].upper()
        ),
        "kind": "language_feature",
        "status": "needs_review",
        "payload": payload,
        "source_record_ids": [entry_id],
        "evidence": evidence,
        "conflicts": entry.get("conflicts", []),
        "score": int(entry.get("evidence_score", 0)),
        "review_notes": [
            "Verify meaning separation, context gates, negative cases, "
            "boundary cases, and runtime safety."
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    proposals: list[dict[str, Any]] = []
    ids: set[str] = set()
    for path in args.input:
        for entry in _load(path):
            item = _proposal(entry, path)
            if item["proposal_id"] in ids:
                continue
            ids.add(item["proposal_id"])
            proposals.append(item)
    if not proposals:
        raise ValueError("no language feature candidates were collected")
    proposals.sort(key=lambda item: (-item["score"], item["proposal_id"]))
    core = {
        "schema_version": PROPOSAL_SCHEMA_VERSION,
        "batch_id": args.batch_id,
        "status": "needs_review",
        "input_files": [str(path) for path in args.input],
        "counts": {"language_feature": len(proposals)},
        "proposals": proposals,
    }
    encoded = json.dumps(
        core,
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    core["bundle_sha256"] = hashlib.sha256(encoded).hexdigest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        yaml.safe_dump(core, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print({
        "status": "OK",
        "proposals": len(proposals),
        "output": str(args.out),
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
