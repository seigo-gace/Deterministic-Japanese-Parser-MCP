#!/usr/bin/env python3
"""Inspect and source-lock large public dependency datasets without repackaging raw data.

The tool is intentionally build-time only. It does not invent lexical meanings.
For relation corpora, it preserves source provenance and enough format evidence to
build a deterministic adapter in a subsequent atomic step.
"""
from __future__ import annotations

import argparse
import bz2
import hashlib
import json
from pathlib import Path
import tarfile
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("sources"), list):
        raise RuntimeError("invalid source manifest")
    return value


def source_spec(manifest: dict[str, Any], source_id: str) -> dict[str, Any]:
    matches = [item for item in manifest["sources"] if item.get("id") == source_id]
    if len(matches) != 1:
        raise RuntimeError(f"source id not unique: {source_id}")
    return matches[0]


def best_decode(payload: bytes) -> tuple[str, str]:
    candidates: list[tuple[int, str, str]] = []
    for encoding in ("utf-8", "euc_jp", "cp932"):
        text = payload.decode(encoding, errors="replace")
        candidates.append((text.count("\ufffd"), encoding, text))
    _, encoding, text = min(candidates, key=lambda item: (item[0], candidates.index(item)))
    return encoding, text


def stream_bz2_sample(handle, *, max_decompressed_bytes: int = 512 * 1024) -> bytes:
    decoder = bz2.BZ2Decompressor()
    output = bytearray()
    while len(output) < max_decompressed_bytes:
        chunk = handle.read(1024 * 1024)
        if not chunk:
            break
        decoded = decoder.decompress(chunk, max_length=max_decompressed_bytes - len(output))
        output.extend(decoded)
        if decoder.eof:
            break
    return bytes(output)


def inspect_nict_wikipedia_dependency(
    manifest_path: Path,
    archive_path: Path,
    report_path: Path,
    lock_path: Path,
    sample_path: Path,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    spec = source_spec(manifest, "nict-wikipedia-dependency-v1.0")
    source_sha = sha256_file(archive_path)
    expected_sha = str(spec.get("expected_source_sha256") or "").strip().casefold()
    if expected_sha and expected_sha != source_sha.casefold():
        raise RuntimeError(
            f"source digest mismatch: expected={expected_sha} actual={source_sha}"
        )

    members: list[dict[str, Any]] = []
    body_member = None
    readme_member = None
    with tarfile.open(archive_path, mode="r:gz") as archive:
        for member in archive.getmembers():
            members.append(
                {
                    "name": member.name,
                    "size": member.size,
                    "type": "file" if member.isfile() else "other",
                }
            )
            if member.isfile() and member.name.endswith("DEP_WIKIPEDIA_V1.0.bz2"):
                body_member = member
            if member.isfile() and member.name.endswith("DEP_WIKIPEDIA_V1.0_README.doc"):
                readme_member = member

        if body_member is None:
            raise RuntimeError("dependency body DEP_WIKIPEDIA_V1.0.bz2 not found")
        if readme_member is None:
            raise RuntimeError("DEP_WIKIPEDIA_V1.0_README.doc not found")

        body = archive.extractfile(body_member)
        if body is None:
            raise RuntimeError("cannot stream dependency body")
        sample_bytes = stream_bz2_sample(body)
        sample_encoding, sample_text = best_decode(sample_bytes)
        sample_lines = sample_text.splitlines()[:200]
        if not sample_lines:
            raise RuntimeError("dependency body sample is empty")
        sample_path.parent.mkdir(parents=True, exist_ok=True)
        sample_path.write_text("\n".join(sample_lines) + "\n", encoding="utf-8")

        readme = archive.extractfile(readme_member)
        if readme is None:
            raise RuntimeError("cannot read dependency README")
        readme_bytes = readme.read()
        readme_sha = hashlib.sha256(readme_bytes).hexdigest()

    report = {
        "source_id": spec["id"],
        "title": spec["title"],
        "status": "SOURCE_ACQUIRED_FORMAT_INSPECTED",
        "source_url": spec["url"],
        "homepage": spec["homepage"],
        "license": spec["license"],
        "license_url": spec["license_url"],
        "attribution": spec["attribution"],
        "source_bytes": archive_path.stat().st_size,
        "source_sha256": source_sha,
        "archive_member_count": len(members),
        "archive_members": members,
        "body_member": body_member.name,
        "body_member_compressed_bytes": body_member.size,
        "readme_member": readme_member.name,
        "readme_sha256": readme_sha,
        "sample_encoding": sample_encoding,
        "sample_lines": len(sample_lines),
        "sample_sha256": sha256_file(sample_path),
        "llm_api_used": False,
        "web_scraping_used": False,
        "raw_source_committed": False,
        "meaning_policy": (
            "This source is syntactic dependency/frequency evidence, not a lexical "
            "definition dictionary. Lexical meanings must be joined from separately "
            "licensed semantic sources; no meaning is invented from dependency pairs."
        ),
    }
    lock = {
        "source_id": spec["id"],
        "source_url": spec["url"],
        "version": spec["version"],
        "source_sha256": source_sha,
        "source_bytes": archive_path.stat().st_size,
        "license": spec["license"],
        "license_url": spec["license_url"],
        "attribution": spec["attribution"],
        "body_member": body_member.name,
        "readme_sha256": readme_sha,
        "lock_state": "computed-digest-needs-canonical-lock",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lock_path.write_text(
        json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--sample", type=Path, required=True)
    args = parser.parse_args()
    result = inspect_nict_wikipedia_dependency(
        args.manifest,
        args.archive,
        args.report,
        args.lock,
        args.sample,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
