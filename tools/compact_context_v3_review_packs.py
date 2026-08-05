#!/usr/bin/env python3
"""Create a compact, public index from Stage 3 review packs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def compact_pack_index(
    packs_text: str,
    *,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    digest = hashlib.sha256(packs_text.encode("utf-8")).hexdigest()
    if expected_sha256 and digest != expected_sha256:
        raise ValueError(
            f"review pack digest mismatch: expected={expected_sha256} actual={digest}"
        )
    packs = [
        json.loads(line)
        for line in packs_text.splitlines()
        if line.strip()
    ]
    if not packs:
        raise ValueError("no review packs")
    entry_ids: list[str] = []
    compact_packs: list[list[Any]] = []
    required_checks = packs[0].get("required_checks", [])
    for pack in packs:
        if pack.get("required_checks", []) != required_checks:
            raise ValueError(f"required checks differ: {pack.get('pack_id')}")
        ids = list(pack.get("entry_ids", []))
        surfaces = list(pack.get("surfaces", []))
        if len(ids) != len(surfaces) or len(ids) != int(pack.get("entry_count", 0)):
            raise ValueError(f"pack entry mismatch: {pack.get('pack_id')}")
        if pack.get("runtime_promotion_allowed") is not False:
            raise ValueError(f"runtime promotion boundary missing: {pack.get('pack_id')}")
        entry_ids.extend(ids)
        compact_packs.append([
            pack["pack_id"],
            pack["category"],
            pack["primary_status"],
            [[entry_id, surface] for entry_id, surface in zip(ids, surfaces)],
        ])
    if len(entry_ids) != 5000 or len(set(entry_ids)) != 5000:
        raise ValueError(
            f"review pack coverage mismatch: rows={len(entry_ids)} "
            f"unique={len(set(entry_ids))}"
        )
    return {
        "schema_version": "1.0.0",
        "source_review_packs_sha256": digest,
        "pack_size": max(len(pack[3]) for pack in compact_packs),
        "pack_count": len(compact_packs),
        "entry_count": len(entry_ids),
        "runtime_promotion_allowed": False,
        "required_checks": required_checks,
        "packs": compact_packs,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    packs_text = args.input.read_text(encoding="utf-8")
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    index = compact_pack_index(
        packs_text,
        expected_sha256=summary["review_packs_sha256"],
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(index, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({
        "status": "WRITTEN",
        "packs": index["pack_count"],
        "entries": index["entry_count"],
        "runtime_promoted_entries": 0,
        "output": str(args.output),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
