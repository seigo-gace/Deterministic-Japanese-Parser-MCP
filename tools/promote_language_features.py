#!/usr/bin/env python3
"""Transactionally promote reviewed language_feature proposals and compile assets."""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dictionary_supply.proposals import load_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()
    bundle = load_bundle(args.bundle)
    approved = [
        item
        for item in bundle.get("proposals", [])
        if item.get("kind") == "language_feature"
        and item.get("status") == "approved"
    ]
    if not approved:
        raise ValueError("no approved language_feature proposals")
    entries = []
    for proposal in approved:
        review = proposal.get("review", {})
        for key in (
            "positive_examples", "negative_examples", "boundary_examples"
        ):
            if not review.get(key):
                raise ValueError(f"{key} is required: {proposal['proposal_id']}")
        payload = dict(proposal["payload"])
        payload["source_proposal_id"] = proposal["proposal_id"]
        payload["review"] = {
            "notes": review.get("notes", []),
            "positive_examples": review["positive_examples"],
            "negative_examples": review["negative_examples"],
            "boundary_examples": review["boundary_examples"],
        }
        entries.append(payload)
    output = (
        ROOT
        / "dictionaries/system/language_features.d"
        / f"generated-{args.batch_id}.yaml"
    )
    compiled = ROOT / "dictionaries/system/compiled/language_features.d"
    approvals_path = (
        ROOT / "dictionaries/system/language_features.d/approvals.yaml"
    )
    if output.exists():
        raise FileExistsError(output)
    document = {
        "schema_version": "1.0.0",
        "version": args.batch_id,
        "entries": entries,
    }
    output_text = yaml.safe_dump(
        document,
        allow_unicode=True,
        sort_keys=False,
    )
    if not args.apply:
        print(output_text)
        return 0
    backup = compiled.parent / "language_features.d.rollback"
    approvals_backup = approvals_path.with_suffix(".yaml.rollback")
    if compiled.exists():
        shutil.copytree(compiled, backup)
    if approvals_path.exists():
        shutil.copy2(approvals_path, approvals_backup)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(output_text, encoding="utf-8")
        approvals = yaml.safe_load(
            approvals_path.read_text(encoding="utf-8")
        ) or {}
        approvals.setdefault("schema_version", "1.0.0")
        fragments = approvals.setdefault("approved_fragments", {})
        fragments[output.name] = {
            "status": "approved",
            "source_sha256": hashlib.sha256(
                output_text.encode("utf-8")
            ).hexdigest(),
            "review_id": (
                f"review-bundle:{bundle.get('batch_id', args.batch_id)}"
            ),
        }
        approvals_path.write_text(
            yaml.safe_dump(approvals, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        subprocess.run(
            [sys.executable, str(ROOT / "tools/compile_language_features.py")],
            cwd=ROOT,
            check=True,
        )
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools/compile_language_features.py"),
                "--check",
            ],
            cwd=ROOT,
            check=True,
        )
        if not args.skip_tests:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/test_language_feature_runtime.py",
                    "tests/test_compiled_language_assets.py",
                ],
                cwd=ROOT,
                check=True,
            )
    except Exception:
        output.unlink(missing_ok=True)
        if compiled.exists():
            shutil.rmtree(compiled)
        if backup.exists():
            shutil.move(str(backup), str(compiled))
        if approvals_backup.exists():
            shutil.move(str(approvals_backup), str(approvals_path))
        raise
    finally:
        if backup.exists():
            shutil.rmtree(backup)
        approvals_backup.unlink(missing_ok=True)
    print({
        "status": "PROMOTED",
        "entries": len(entries),
        "output": str(output),
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
