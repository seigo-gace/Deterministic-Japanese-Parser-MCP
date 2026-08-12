"""Safe, deterministic intake for already-collected source artifacts.

The intake layer proves provenance, selects only declared payloads and scans every
selected byte with a declared parser family.  It deliberately stops before semantic
normalisation, adapter conversion, approval or runtime promotion.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
import codecs
import csv
import fnmatch
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import tempfile
from typing import Any, BinaryIO
import xml.etree.ElementTree as ET
import zipfile


PROFILE_SCHEMA_VERSION = "1.0.0"
INTAKE_SCHEMA_VERSION = "1.0.0"
LANES = {"C", "S", "R", "Q", "I"}
PARSER_FAMILIES = {
    "commented-sequence",
    "delimited-table",
    "streaming-xml",
    "json-corpus",
    "conllu",
    "skk",
    "knp",
    "jsonl",
    "rdf-xml",
    "archive-index",
}
HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
ADAPTER_SOURCE_ROLES = {
    "domain-term", "education", "entity", "error-normalization", "familiarity",
    "frequency", "knowledge-relation", "lexical-definition", "lexical-relation",
    "morphology", "orthography", "pragmatics", "pronunciation", "semantic-class",
    "sentiment", "syntax", "temporal", "translation", "usage",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_archive_name(name: str) -> str:
    if "\\" in name:
        raise ValueError(f"archive path uses backslash: {name}")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe archive path: {name}")
    return str(path)


def _walk(value: Any) -> Iterator[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key), child
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _lock_source_id(lock: dict[str, Any]) -> str:
    for key, value in _walk(lock):
        if key.lower() in {"source_id", "source-id"} and isinstance(value, str):
            return value.strip()
    return ""


def _lock_proves_raw(lock: dict[str, Any], digest: str, size: int) -> tuple[bool, bool]:
    digest_found = False
    size_found = False
    for key, value in _walk(lock):
        lowered = key.lower()
        if ("sha" in lowered or "digest" in lowered) and isinstance(value, str):
            candidate = value.lower().removeprefix("sha256:")
            if HEX64.fullmatch(candidate) and candidate == digest:
                digest_found = True
        if ("byte" in lowered or "size" in lowered) and not isinstance(value, bool):
            try:
                if int(value) == size:
                    size_found = True
            except (TypeError, ValueError):
                pass
    return digest_found, size_found


def load_profiles(path: Path) -> dict[str, Any]:
    profiles = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(profiles, dict) or profiles.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise ValueError("unsupported source payload profile schema")
    sources = profiles.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("source payload profiles are required")
    expected = int(profiles.get("expected_source_count", 0))
    if expected != len(sources):
        raise ValueError("expected_source_count does not match source profiles")
    names: set[str] = set()
    source_ids: set[str] = set()
    for profile in sources:
        name = str(profile.get("artifact_name") or "")
        source_id = str(profile.get("source_id") or "")
        if not name or (name in names and profile.get("artifact_kind", "harvest") != "collection"):
            raise ValueError(f"artifact_name must be unique: {name}")
        if not source_id or source_id in source_ids:
            raise ValueError(f"source_id must be unique: {source_id}")
        names.add(name)
        source_ids.add(source_id)
        if profile.get("rights_lane") not in LANES:
            raise ValueError(f"invalid rights lane: {source_id}")
        if profile.get("parser_family") not in PARSER_FAMILIES:
            raise ValueError(f"invalid parser family: {source_id}")
        if not profile.get("payload_globs"):
            raise ValueError(f"payload_globs required: {source_id}")
        roles = profile.get("source_roles") or []
        if not roles or any(role not in ADAPTER_SOURCE_ROLES for role in roles):
            raise ValueError(f"source_roles are not adapter-compatible: {source_id}:{roles}")
        encodings = profile.get("encodings") or []
        if profile["parser_family"] not in {"streaming-xml", "rdf-xml", "archive-index"} and not encodings:
            raise ValueError(f"declared encodings required: {source_id}")
        for encoding in encodings:
            codecs.lookup(str(encoding))
        public_expected = profile["rights_lane"] == "C"
        if bool(profile.get("public_runtime_eligible")) != public_expected:
            raise ValueError(f"public eligibility/lane mismatch: {source_id}")
    return profiles


def validate_intake_manifest(manifest: dict[str, Any]) -> None:
    """Validate the exact handoff contract between acquisition and source adapters."""
    if manifest.get("source_intake_schema_version") != INTAKE_SCHEMA_VERSION:
        raise ValueError("unsupported source intake manifest schema")
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("source intake manifest requires sources")
    if int(manifest.get("source_count", 0)) != len(sources):
        raise ValueError("source intake manifest source_count mismatch")
    source_ids: set[str] = set()
    logical_ids: set[str] = set()
    for source in sources:
        source_id = str(source.get("source_id") or "")
        if not source_id or source_id in source_ids:
            raise ValueError(f"invalid or duplicate intake source_id: {source_id}")
        source_ids.add(source_id)
        logical_ids.add(str(source.get("logical_source_id") or source_id))
        if source.get("rights_lane") not in LANES:
            raise ValueError(f"invalid intake rights lane: {source_id}")
        if source.get("parser_family") not in PARSER_FAMILIES:
            raise ValueError(f"invalid intake parser family: {source_id}")
        roles = source.get("source_roles") or []
        if not roles or any(role not in ADAPTER_SOURCE_ROLES for role in roles):
            raise ValueError(f"intake source roles are not adapter-compatible: {source_id}")
        if bool(source.get("public_runtime_eligible")) != (source["rights_lane"] == "C"):
            raise ValueError(f"intake public eligibility/lane mismatch: {source_id}")
        if not source.get("payloads"):
            raise ValueError(f"intake source has no selected payload: {source_id}")
        records = int(source.get("parsed_records", source.get("parser_probe_records", 0)))
        if records < 1 or source.get("factory_ready") is not True:
            raise ValueError(f"intake source is not factory-ready: {source_id}")
        if source.get("automatic_approval") is not False:
            raise ValueError(f"automatic approval boundary missing: {source_id}")
        if source.get("automatic_runtime_promotion") is not False:
            raise ValueError(f"automatic runtime promotion boundary missing: {source_id}")
    if int(manifest.get("factory_ready_source_count", 0)) != len(sources):
        raise ValueError("not every intake source is factory-ready")
    if int(manifest.get("unique_logical_source_count", 0)) != len(logical_ids):
        raise ValueError("unique logical source count mismatch")


def _matching_names(names: list[str], globs: list[str]) -> list[str]:
    return sorted(
        name
        for name in names
        if any(fnmatch.fnmatchcase(name, pattern) for pattern in globs)
    )


def _decoded_lines(open_binary: Callable[[], BinaryIO], encoding: str) -> Iterator[str]:
    handle = open_binary()
    text = io.TextIOWrapper(handle, encoding=encoding, errors="strict", newline="")
    try:
        yield from text
    finally:
        text.close()


def _scan_text(profile: dict[str, Any], open_binary: Callable[[], BinaryIO]) -> tuple[int, str]:
    family = profile["parser_family"]
    last_error: UnicodeError | None = None
    for encoding in list(profile.get("encodings") or []):
        count = 0
        lines = _decoded_lines(open_binary, encoding)
        try:
            if family == "delimited-table" and profile.get("delimiter"):
                reader = csv.reader(lines, delimiter=str(profile["delimiter"]), strict=True)
                minimum = int(profile.get("minimum_columns", 1))
                for row in reader:
                    if not row or (row[0].lstrip().startswith("#")):
                        continue
                    if len(row) < minimum:
                        raise ValueError(f"delimited row has fewer than {minimum} columns")
                    count += 1
            else:
                for line in lines:
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#") or stripped.startswith(";;"):
                        continue
                    if family == "conllu" and len(stripped.split("\t")) < 10:
                        raise ValueError("CoNLL-U token row has fewer than 10 columns")
                    if family == "skk" and "/" not in stripped:
                        raise ValueError("SKK entry has no candidate delimiter")
                    if family == "knp" and not (
                        stripped == "EOS" or stripped.startswith(("* ", "+ ", "# ")) or " " in stripped
                    ):
                        raise ValueError("unrecognised KNP row")
                    count += 1
            return count, encoding
        except UnicodeError as exc:
            last_error = exc
    raise ValueError(
        f"none of the declared encodings decoded the payload: {profile.get('encodings')}"
    ) from last_error


def _scan_json(open_binary: Callable[[], BinaryIO], encodings: list[str]) -> tuple[int, str]:
    last_error: UnicodeError | None = None
    for encoding in encodings:
        try:
            value = json.load(io.StringIO("".join(_decoded_lines(open_binary, encoding))))
        except UnicodeError as exc:
            last_error = exc
            continue
        if isinstance(value, list):
            return len(value), encoding
        if isinstance(value, dict):
            return max(1, len(value)), encoding
        raise ValueError("JSON corpus root must be an object or array")
    raise ValueError(f"none of the declared encodings decoded JSON: {encodings}") from last_error


def _scan_xml(open_binary: Callable[[], BinaryIO], target_tags: list[str]) -> tuple[int, str]:
    targets = set(target_tags)
    count = 0
    handle = open_binary()
    try:
        for _event, element in ET.iterparse(handle, events=("end",)):
            local = element.tag.rsplit("}", 1)[-1]
            if not targets or local in targets:
                count += 1
            element.clear()
    finally:
        handle.close()
    return count, "xml-declared"


def scan_payload(
    profile: dict[str, Any],
    open_binary: Callable[[], BinaryIO],
) -> tuple[int, str]:
    family = profile["parser_family"]
    if family == "streaming-xml":
        return _scan_xml(open_binary, list(profile.get("xml_target_tags") or []))
    if family == "json-corpus":
        return _scan_json(open_binary, list(profile.get("encodings") or []))
    return _scan_text(profile, open_binary)


def _gzip_open(path: Path) -> BinaryIO:
    return gzip.open(path, "rb")


def _plain_open(path: Path) -> BinaryIO:
    return path.open("rb")


def inspect_collected_artifact(
    artifact_zip: Path,
    artifact: dict[str, Any],
    profile: dict[str, Any],
    limits: dict[str, Any],
) -> dict[str, Any]:
    max_members = int(limits.get("max_archive_members", 25000))
    max_payload_bytes = int(limits.get("max_total_uncompressed_bytes_per_source", 2_000_000_000))
    max_ratio = float(limits.get("max_compression_ratio", 250.0))
    with zipfile.ZipFile(artifact_zip) as outer:
        outer_names = [_safe_archive_name(info.filename) for info in outer.infolist() if not info.is_dir()]
        lock_names = [name for name in outer_names if PurePosixPath(name).name == "source-lock.json"]
        if len(lock_names) != 1:
            raise ValueError(f"exactly one source-lock.json required: {artifact_zip}")
        raw_names = [name for name in outer_names if name not in lock_names]
        if len(raw_names) != 1:
            raise ValueError(f"exactly one raw payload required: {artifact_zip}")
        lock = json.loads(outer.read(lock_names[0]).decode("utf-8"))
        if not isinstance(lock, dict):
            raise ValueError("source-lock.json must be an object")
        with tempfile.TemporaryDirectory() as directory:
            raw_path = Path(directory) / PurePosixPath(raw_names[0]).name
            digest = hashlib.sha256()
            size = 0
            with outer.open(raw_names[0]) as source, raw_path.open("wb") as destination:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
                    size += len(chunk)
                    destination.write(chunk)
            raw_digest = digest.hexdigest()
            digest_proven, size_proven = _lock_proves_raw(lock, raw_digest, size)
            if not digest_proven or not size_proven:
                raise ValueError(f"source-lock does not prove raw digest and bytes: {profile['source_id']}")
            locked_source_id = _lock_source_id(lock)
            if locked_source_id and locked_source_id != profile["source_id"]:
                raise ValueError(
                    f"source id mismatch: profile={profile['source_id']} lock={locked_source_id}"
                )

            payloads: list[dict[str, Any]] = []
            if zipfile.is_zipfile(raw_path):
                inner = zipfile.ZipFile(raw_path)
                try:
                    infos = [info for info in inner.infolist() if not info.is_dir()]
                    if len(infos) > max_members:
                        raise ValueError(f"inner archive member limit exceeded: {profile['source_id']}")
                    names = [_safe_archive_name(info.filename) for info in infos]
                    selected_names = _matching_names(names, list(profile["payload_globs"]))
                    if len(selected_names) < int(profile.get("minimum_payloads", 1)):
                        raise ValueError(f"declared payload not found: {profile['source_id']}")
                    info_by_name = {info.filename: info for info in infos}
                    total = sum(info_by_name[name].file_size for name in selected_names)
                    if total > max_payload_bytes:
                        raise ValueError(f"selected payload byte limit exceeded: {profile['source_id']}")
                    for name in selected_names:
                        info = info_by_name[name]
                        ratio = info.file_size / max(1, info.compress_size)
                        if ratio > max_ratio:
                            raise ValueError(f"compression ratio limit exceeded: {profile['source_id']}:{name}")
                        def opener(name: str = name) -> BinaryIO:
                            return inner.open(name, "r")
                        record_count, encoding = scan_payload(profile, opener)
                        if record_count < int(profile.get("minimum_records", 1)):
                            raise ValueError(f"payload has too few records: {profile['source_id']}:{name}")
                        payloads.append(
                            {
                                "path": name,
                                "bytes": info.file_size,
                                "crc32": f"{info.CRC:08x}",
                                "encoding": encoding,
                                "parsed_records": record_count,
                            }
                        )
                finally:
                    inner.close()
            else:
                name = raw_path.name
                if not _matching_names([name], list(profile["payload_globs"])):
                    raise ValueError(f"direct payload does not match allowlist: {profile['source_id']}:{name}")
                opener = (lambda: _gzip_open(raw_path)) if raw_path.suffix.lower() == ".gz" else (lambda: _plain_open(raw_path))
                record_count, encoding = scan_payload(profile, opener)
                if record_count < int(profile.get("minimum_records", 1)):
                    raise ValueError(f"payload has too few records: {profile['source_id']}:{name}")
                payloads.append(
                    {
                        "path": name,
                        "bytes": size,
                        "sha256": raw_digest,
                        "encoding": encoding,
                        "parsed_records": record_count,
                    }
                )

    return {
        "source_id": profile["source_id"],
        "artifact_id": int(artifact["id"]),
        "artifact_name": profile["artifact_name"],
        "workflow_run_id": int(artifact.get("workflow_run_id", 0)),
        "source_lock": lock,
        "raw_path": raw_names[0],
        "raw_sha256": raw_digest,
        "raw_bytes": size,
        "rights_lane": profile["rights_lane"],
        "public_runtime_eligible": bool(profile["public_runtime_eligible"]),
        "parser_family": profile["parser_family"],
        "source_roles": list(profile.get("source_roles") or []),
        "payloads": payloads,
        "parsed_records": sum(item["parsed_records"] for item in payloads),
        "factory_ready": True,
        "automatic_approval": False,
        "automatic_runtime_promotion": False,
    }
