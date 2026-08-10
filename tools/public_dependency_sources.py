#!/usr/bin/env python3
"""Inspect and source-lock large public dependency datasets without repackaging raw data.

The tool is intentionally build-time only. It never invents lexical meanings.
For relation corpora it preserves provenance, archive membership, format evidence,
and a deterministic sample so a later normalization stage can be implemented from
observed source structure rather than filename or schema assumptions.
"""
from __future__ import annotations

import argparse
import bz2
from collections import Counter
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile
import tempfile
from typing import Any

SOURCE_ID = "nict-wikipedia-dependency-v1.0"
BODY_BASENAME = "DEP_WIKIPEDIA_V1.0.bz2"


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
    candidates: list[tuple[int, int, str, str]] = []
    encodings = ("utf-8", "euc_jp", "cp932")
    for order, encoding in enumerate(encodings):
        text = payload.decode(encoding, errors="replace")
        candidates.append((text.count("\ufffd"), order, encoding, text))
    _, _, encoding, text = min(candidates)
    return encoding, text


def stream_bz2_sample(handle, *, max_decompressed_bytes: int = 2 * 1024 * 1024) -> bytes:
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


def _basename(name: str) -> str:
    return PurePosixPath(name).name


def _readme_priority(name: str) -> tuple[int, str]:
    base = _basename(name).casefold()
    exact = "dep_wikipedia_v1.0_readme.doc"
    if base == exact:
        return (0, name)
    if "dep_wikipedia" in base and "readme" in base:
        return (1, name)
    if "readme" in base:
        return (2, name)
    return (9, name)


def _choose_members(archive: tarfile.TarFile) -> tuple[tarfile.TarInfo, tarfile.TarInfo | None, list[dict[str, Any]]]:
    members: list[dict[str, Any]] = []
    body_candidates: list[tarfile.TarInfo] = []
    readme_candidates: list[tarfile.TarInfo] = []
    for member in archive.getmembers():
        members.append(
            {
                "name": member.name,
                "basename": _basename(member.name),
                "size": member.size,
                "type": "file" if member.isfile() else "other",
            }
        )
        if not member.isfile():
            continue
        base = _basename(member.name)
        if base.casefold() == BODY_BASENAME.casefold():
            body_candidates.append(member)
        if "readme" in base.casefold():
            readme_candidates.append(member)

    if len(body_candidates) != 1:
        raise RuntimeError(
            f"dependency body not unique: expected={BODY_BASENAME!r} "
            f"matches={[member.name for member in body_candidates]}"
        )
    readme_member = (
        sorted(readme_candidates, key=lambda member: _readme_priority(member.name))[0]
        if readme_candidates
        else None
    )
    return body_candidates[0], readme_member, members


def _is_int(value: str) -> bool:
    try:
        int(value.strip())
        return True
    except ValueError:
        return False


def analyze_sample(lines: list[str]) -> dict[str, Any]:
    nonempty = [line for line in lines if line.strip()]
    tab_fields = Counter(len(line.split("\t")) for line in nonempty)
    whitespace_fields = Counter(len(line.split()) for line in nonempty)
    tab_numeric_tail = sum(
        1 for line in nonempty if "\t" in line and _is_int(line.split("\t")[-1])
    )
    whitespace_numeric_tail = sum(
        1 for line in nonempty if len(line.split()) >= 2 and _is_int(line.split()[-1])
    )
    count = len(nonempty)
    format_guess = "unknown"
    if count and tab_numeric_tail / count >= 0.95:
        common_tab_fields = tab_fields.most_common(1)[0][0]
        format_guess = f"tab-separated-{common_tab_fields}-fields-numeric-tail"
    elif count and whitespace_numeric_tail / count >= 0.95:
        common_ws_fields = whitespace_fields.most_common(1)[0][0]
        format_guess = f"whitespace-separated-{common_ws_fields}-fields-numeric-tail"
    return {
        "nonempty_lines": count,
        "tab_field_histogram": {str(k): v for k, v in sorted(tab_fields.items())},
        "whitespace_field_histogram": {
            str(k): v for k, v in sorted(whitespace_fields.items())
        },
        "tab_numeric_tail_lines": tab_numeric_tail,
        "whitespace_numeric_tail_lines": whitespace_numeric_tail,
        "format_guess": format_guess,
    }


def inspect_nict_wikipedia_dependency(
    manifest_path: Path,
    archive_path: Path,
    report_path: Path,
    lock_path: Path,
    sample_path: Path,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    spec = source_spec(manifest, SOURCE_ID)
    source_sha = sha256_file(archive_path)
    expected_sha = str(spec.get("expected_source_sha256") or "").strip().casefold()
    if expected_sha and expected_sha != source_sha.casefold():
        raise RuntimeError(
            f"source digest mismatch: expected={expected_sha} actual={source_sha}"
        )

    with tarfile.open(archive_path, mode="r:gz") as archive:
        body_member, readme_member, members = _choose_members(archive)
        body = archive.extractfile(body_member)
        if body is None:
            raise RuntimeError("cannot stream dependency body")
        sample_bytes = stream_bz2_sample(body)
        sample_encoding, sample_text = best_decode(sample_bytes)
        sample_lines = sample_text.splitlines()[:1000]
        if not sample_lines:
            raise RuntimeError("dependency body sample is empty")
        sample_path.parent.mkdir(parents=True, exist_ok=True)
        sample_path.write_text("\n".join(sample_lines) + "\n", encoding="utf-8")
        sample_analysis = analyze_sample(sample_lines)

        readme_sha = None
        readme_bytes = b""
        if readme_member is not None:
            readme = archive.extractfile(readme_member)
            if readme is None:
                raise RuntimeError("cannot read detected dependency README")
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
        "readme_member": readme_member.name if readme_member else None,
        "readme_detected": readme_member is not None,
        "readme_sha256": readme_sha,
        "sample_encoding": sample_encoding,
        "sample_lines": len(sample_lines),
        "sample_sha256": sha256_file(sample_path),
        "sample_analysis": sample_analysis,
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
        "readme_member": readme_member.name if readme_member else None,
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


def self_test() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        manifest_path = root / "manifest.json"
        archive_path = root / "test.tar.gz"
        report_path = root / "report.json"
        lock_path = root / "lock.json"
        sample_path = root / "sample.txt"
        manifest_path.write_text(
            json.dumps(
                {
                    "sources": [
                        {
                            "id": SOURCE_ID,
                            "title": "test",
                            "url": "https://example.invalid/source",
                            "homepage": "https://example.invalid/",
                            "version": "test",
                            "license": "test-license",
                            "license_url": "https://example.invalid/license",
                            "attribution": "test-attribution",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        raw = "係り元\t係り先\t12\n別の元\t別の先\t3\n".encode("utf-8")
        body_bytes = bz2.compress(raw)
        with tarfile.open(archive_path, mode="w:gz") as archive:
            body_info = tarfile.TarInfo(name=f"nested/{BODY_BASENAME}")
            body_info.size = len(body_bytes)
            archive.addfile(body_info, io.BytesIO(body_bytes))
            readme_bytes = b"test readme"
            readme_info = tarfile.TarInfo(name="nested/README.txt")
            readme_info.size = len(readme_bytes)
            archive.addfile(readme_info, io.BytesIO(readme_bytes))
        report = inspect_nict_wikipedia_dependency(
            manifest_path, archive_path, report_path, lock_path, sample_path
        )
        if report["sample_analysis"]["format_guess"] != "tab-separated-3-fields-numeric-tail":
            raise RuntimeError(f"self-test format inference failed: {report['sample_analysis']}")
        if report["readme_member"] != "nested/README.txt":
            raise RuntimeError("self-test README detection failed")
        return {
            "status": "PASS",
            "body_member": report["body_member"],
            "readme_member": report["readme_member"],
            "format_guess": report["sample_analysis"]["format_guess"],
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--lock", type=Path)
    parser.add_argument("--sample", type=Path)
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test(), ensure_ascii=False, sort_keys=True))
        return 0
    required = {
        "manifest": args.manifest,
        "archive": args.archive,
        "report": args.report,
        "lock": args.lock,
        "sample": args.sample,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        parser.error(f"required arguments missing: {', '.join(missing)}")
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
