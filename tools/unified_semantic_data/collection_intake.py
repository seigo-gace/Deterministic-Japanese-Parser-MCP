"""Validate multi-source collection artifacts and make them factory-addressable."""
from __future__ import annotations

import bz2
import fnmatch
import gzip
import hashlib
import io
import json
import lzma
from pathlib import Path, PurePosixPath
import re
import tarfile
import tempfile
from typing import Any, BinaryIO, Callable
import xml.etree.ElementTree as ET
import zipfile

from .raw_intake import _safe_archive_name


HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _hash_stream(handle: BinaryIO) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def _collect_declared_digests(value: Any, output: set[str]) -> None:
    if isinstance(value, dict):
        for child in value.values():
            _collect_declared_digests(child, output)
    elif isinstance(value, list):
        for child in value:
            _collect_declared_digests(child, output)
    elif isinstance(value, str):
        candidate = value.lower().removeprefix("sha256:")
        if HEX64.fullmatch(candidate):
            output.add(candidate)


def _metadata_digests(archive: zipfile.ZipFile) -> set[str]:
    output: set[str] = set()
    for info in archive.infolist():
        if info.is_dir() or info.file_size > 10_000_000 or not info.filename.endswith(".json"):
            continue
        try:
            value = json.loads(archive.read(info))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        _collect_declared_digests(value, output)
    return output


def _open_decompressed(path: Path) -> BinaryIO:
    lowered = path.name.lower()
    if lowered.endswith(".gz"):
        return gzip.open(path, "rb")
    if lowered.endswith(".bz2"):
        return bz2.open(path, "rb")
    if lowered.endswith(".xz"):
        return lzma.open(path, "rb")
    return path.open("rb")


def _probe_text(
    opener: Callable[[], BinaryIO], encodings: list[str], *, delimiter: str | None, limit: int
) -> tuple[int, str]:
    last_error: UnicodeError | None = None
    for encoding in encodings:
        count = 0
        delimiter_seen = delimiter is None
        try:
            with opener() as raw, io.TextIOWrapper(
                raw, encoding=encoding, errors="strict", newline=""
            ) as text:
                for line in text:
                    stripped = line.strip()
                    if not stripped or stripped.startswith(("#", ";;")):
                        continue
                    if delimiter and delimiter in stripped:
                        delimiter_seen = True
                    count += 1
                    if count >= limit:
                        break
            if not delimiter_seen:
                raise ValueError("declared delimiter missing from probe")
            return count, encoding
        except UnicodeError as exc:
            last_error = exc
    raise ValueError(f"declared encodings cannot decode payload: {encodings}") from last_error


def _probe_jsonl(opener: Callable[[], BinaryIO], encodings: list[str], limit: int) -> tuple[int, str]:
    last_error: (UnicodeError | json.JSONDecodeError) | None = None
    for encoding in encodings:
        count = 0
        try:
            with opener() as raw, io.TextIOWrapper(raw, encoding=encoding, errors="strict") as text:
                for line in text:
                    if not line.strip():
                        continue
                    if not isinstance(json.loads(line), dict):
                        raise ValueError("JSONL record must be an object")
                    count += 1
                    if count >= limit:
                        break
            return count, encoding
        except (UnicodeError, json.JSONDecodeError) as exc:
            last_error = exc
    raise ValueError(f"declared encodings cannot parse JSONL: {encodings}") from last_error


def _probe_xml(opener: Callable[[], BinaryIO], limit: int) -> tuple[int, str]:
    count = 0
    with opener() as handle:
        for _event, element in ET.iterparse(handle, events=("end",)):
            count += 1
            element.clear()
            if count >= limit:
                break
    return count, "xml-declared"


def _probe(profile: dict[str, Any], opener: Callable[[], BinaryIO]) -> tuple[int, str]:
    family = profile["parser_family"]
    limit = int(profile.get("probe_records", 1000))
    encodings = list(profile.get("encodings") or ["utf-8-sig"])
    if family == "archive-index":
        with opener() as handle:
            signature = handle.read(8)
        if not (signature.startswith(b"PK") or signature.startswith(b"version ")):
            raise ValueError("nested archive/pointer signature not recognised")
        return 1, "binary"
    if family in {"streaming-xml", "rdf-xml"}:
        return _probe_xml(opener, limit)
    if family == "jsonl":
        return _probe_jsonl(opener, encodings, limit)
    return _probe_text(
        opener,
        encodings,
        delimiter=profile.get("delimiter"),
        limit=limit,
    )


def _nested_zip_probe(path: Path, profile: dict[str, Any], limits: dict[str, Any]) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        max_members = int(limits.get("max_archive_members", 25000))
        if len(infos) > max_members:
            raise ValueError(f"archive member limit exceeded: {profile['source_id']}")
        names = [_safe_archive_name(info.filename) for info in infos]
        patterns = list(profile.get("inner_payload_globs") or ["*"])
        selected = sorted(
            name for name in names if any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)
        )
        if len(selected) < int(profile.get("minimum_payloads", 1)):
            raise ValueError(f"nested payload missing: {profile['source_id']}")
        info_by_name = {info.filename: info for info in infos}
        probe_count = min(len(selected), int(profile.get("probe_payloads", 3)))
        records = 0
        encodings: set[str] = set()
        for name in selected[:probe_count]:
            def opener(name: str = name) -> BinaryIO:
                raw = archive.open(name, "r")
                lowered = name.lower()
                if lowered.endswith(".xz"):
                    return lzma.LZMAFile(raw)
                if lowered.endswith(".gz"):
                    return gzip.GzipFile(fileobj=raw)
                if lowered.endswith(".bz2"):
                    return bz2.BZ2File(raw)
                return raw
            count, encoding = _probe(profile, opener)
            records += count
            encodings.add(encoding)
        return {
            "nested_format": "zip",
            "nested_member_count": len(infos),
            "selected_payload_count": len(selected),
            "probe_payload_count": probe_count,
            "probe_records": records,
            "probe_encodings": sorted(encodings),
            "selected_uncompressed_bytes": sum(info_by_name[name].file_size for name in selected),
        }


def _nested_tar_probe(path: Path, profile: dict[str, Any]) -> dict[str, Any]:
    with tarfile.open(path, "r:*") as archive:
        members = [member for member in archive.getmembers() if member.isfile()]
        names = [_safe_archive_name(member.name) for member in members]
        patterns = list(profile.get("inner_payload_globs") or ["*"])
        selected = sorted(
            name for name in names if any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)
        )
        if len(selected) < int(profile.get("minimum_payloads", 1)):
            raise ValueError(f"nested payload missing: {profile['source_id']}")
        by_name = {member.name: member for member in members}
        probe_count = min(len(selected), int(profile.get("probe_payloads", 3)))
        records = 0
        encodings: set[str] = set()
        for name in selected[:probe_count]:
            def opener(name: str = name) -> BinaryIO:
                handle = archive.extractfile(by_name[name])
                if handle is None:
                    raise ValueError(f"cannot read tar member: {name}")
                return handle
            count, encoding = _probe(profile, opener)
            records += count
            encodings.add(encoding)
        return {
            "nested_format": "tar",
            "nested_member_count": len(members),
            "selected_payload_count": len(selected),
            "probe_payload_count": probe_count,
            "probe_records": records,
            "probe_encodings": sorted(encodings),
            "selected_uncompressed_bytes": sum(by_name[name].size for name in selected),
        }


def inspect_collection_artifact(
    artifact_zip: Path,
    artifact: dict[str, Any],
    profiles: list[dict[str, Any]],
    limits: dict[str, Any],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    with zipfile.ZipFile(artifact_zip) as outer:
        infos = [info for info in outer.infolist() if not info.is_dir()]
        names = [_safe_archive_name(info.filename) for info in infos]
        info_by_name = {info.filename: info for info in infos}
        declared_digests = _metadata_digests(outer)
        for profile in profiles:
            patterns = list(profile["payload_globs"])
            selected = sorted(
                name for name in names if any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)
            )
            if len(selected) < int(profile.get("minimum_outer_payloads", 1)):
                raise ValueError(f"collection payload missing: {profile['source_id']}")
            payloads: list[dict[str, Any]] = []
            for name in selected:
                info = info_by_name[name]
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / PurePosixPath(name).name
                    with outer.open(name) as source, path.open("wb") as destination:
                        digest = hashlib.sha256()
                        for chunk in iter(lambda: source.read(1024 * 1024), b""):
                            digest.update(chunk)
                            destination.write(chunk)
                    value = digest.hexdigest()
                    proof = value in declared_digests
                    if profile.get("require_declared_digest", True) and not proof:
                        raise ValueError(f"payload digest absent from artifact metadata: {profile['source_id']}:{name}")
                    nested = bool(profile.get("inner_payload_globs"))
                    if nested and zipfile.is_zipfile(path):
                        probe = _nested_zip_probe(path, profile, limits)
                    elif nested and (name.endswith(".tar.bz2") or tarfile.is_tarfile(path)):
                        probe = _nested_tar_probe(path, profile)
                    else:
                        count, encoding = _probe(profile, lambda path=path: _open_decompressed(path))
                        probe = {
                            "probe_records": count,
                            "probe_encodings": [encoding],
                            "selected_payload_count": 1,
                        }
                    if int(probe.get("probe_records", 0)) < 1:
                        raise ValueError(f"parser probe produced no records: {profile['source_id']}:{name}")
                    payloads.append(
                        {
                            "path": name,
                            "bytes": info.file_size,
                            "sha256": value,
                            "digest_declared_in_artifact_metadata": proof,
                            **probe,
                        }
                    )
            results.append(
                {
                    "source_id": profile["source_id"],
                    "logical_source_id": profile.get("logical_source_id", profile["source_id"]),
                    "artifact_id": int(artifact["id"]),
                    "artifact_name": str(artifact["name"]),
                    "workflow_run_id": int(artifact.get("workflow_run_id", 0)),
                    "rights_lane": profile["rights_lane"],
                    "public_runtime_eligible": bool(profile["public_runtime_eligible"]),
                    "parser_family": profile["parser_family"],
                    "source_roles": list(profile.get("source_roles") or []),
                    "payloads": payloads,
                    "parser_probe_records": sum(item["probe_records"] for item in payloads),
                    "factory_ready": True,
                    "full_processing_performed": False,
                    "automatic_approval": False,
                    "automatic_runtime_promotion": False,
                }
            )
    return results
