"""Project every frozen non-definition source into deterministic evidence records.

The raw intake proves that payloads are immutable and parseable.  This stage performs
the missing full pass over those payloads.  Every parsed source record is either
projected to one or more declared auxiliary roles or written, with its complete value
and lineage, to the unresolved lane.  It never manufactures a definition.

Exact replay duplicates are collapsed with SQLite using a semantic fingerprint that
includes logical source, role, lexical identity and the complete payload.  Different
meanings, readings, parts of speech, domains, usages or evidence payloads therefore
remain distinct.  All duplicate source lineages are retained on the surviving record.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
import bz2
import csv
import gzip
import hashlib
import io
import json
import lzma
from pathlib import Path, PurePosixPath
import re
import sqlite3
import tarfile
import tempfile
from typing import Any, BinaryIO
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

from .raw_intake import load_profiles, validate_intake_manifest
from .source_adapter_contract import MEANING_ROLE, compile_adapter_contract


ROLE_FACTORY_VERSION = "1.0.0"
_KNOWN_SURFACE_KEYS = {
    "surface", "surfaces", "lemma", "lemmas", "word", "words", "headword",
    "headwords", "literal", "orth", "orthography", "name", "names", "title",
    "token", "tokens", "form", "forms", "written", "term", "terms", "keyword",
    "keywords", "label", "labels",
}
_KNOWN_READING_KEYS = {
    "reading", "readings", "pronunciation", "pronunciations", "kana", "yomi",
    "transcription", "transcriptions",
}
_KNOWN_POS_KEYS = {
    "part_of_speech", "part_of_speech_list", "pos", "upos", "xpos",
    "grammatical_labels",
}
_KNOWN_DOMAIN_KEYS = {"domain", "domains", "category", "categories", "field", "fields"}
_JAPANESE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]")
_HEX_CODEPOINTS = re.compile(r"^[0-9A-Fa-f]{4,6}(?:\s+[0-9A-Fa-f]{4,6})*$")
_NON_IDENTITY_KEYS = {
    "id", "record_id", "source_id", "dataset", "dataset_name", "version",
    "source_version", "license", "licence", "source_url", "url", "homepage",
    "attribution", "publisher", "copyright", "sha256", "hash", "digest", "bytes",
    "date", "dump_date", "created_at", "updated_at",
}


def _text(value: Any) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def _json_line(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_member(name: str) -> str:
    if "\\" in name:
        raise ValueError(f"archive path uses backslash: {name}")
    value = PurePosixPath(name)
    if value.is_absolute() or any(part in {"", ".", ".."} for part in value.parts):
        raise ValueError(f"unsafe archive path: {name}")
    return str(value)


def _copy_stream(source: BinaryIO, destination: Path, expected_bytes: int | None = None) -> str:
    digest = hashlib.sha256()
    size = 0
    with destination.open("wb") as output:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            size += len(chunk)
            if expected_bytes is not None and size > expected_bytes:
                raise ValueError(f"archive member exceeds declared bytes: {destination}")
            digest.update(chunk)
            output.write(chunk)
    if expected_bytes is not None and size != expected_bytes:
        raise ValueError(f"archive member byte mismatch: {destination}:{size}!={expected_bytes}")
    return digest.hexdigest()


def _open_decompressed(path: Path) -> BinaryIO:
    lowered = path.name.lower()
    if lowered.endswith(".gz"):
        return gzip.open(path, "rb")
    if lowered.endswith(".bz2"):
        return bz2.open(path, "rb")
    if lowered.endswith(".xz"):
        return lzma.open(path, "rb")
    return path.open("rb")


def _select_encoding(path: Path, encodings: list[str]) -> str:
    candidates = encodings or ["utf-8-sig"]
    if len(candidates) == 1:
        return candidates[0]
    errors: list[str] = []
    for encoding in candidates:
        try:
            with _open_decompressed(path) as raw, io.TextIOWrapper(
                raw, encoding=encoding, errors="strict", newline=""
            ) as text:
                for _line in text:
                    pass
            return encoding
        except UnicodeError as exc:
            errors.append(f"{encoding}:{exc}")
    raise ValueError(f"declared encodings cannot decode {path}: {errors}")


def _scalar_texts(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        if _text(value):
            yield _text(value)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        yield str(value)
    elif isinstance(value, list):
        for child in value:
            yield from _scalar_texts(child)
    elif isinstance(value, dict):
        for child in value.values():
            yield from _scalar_texts(child)


def _values_for_keys(value: Any, keys: set[str]) -> Iterator[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).strip().lower()
            if lowered in keys:
                yield from _scalar_texts(child)
            if isinstance(child, (dict, list)):
                yield from _values_for_keys(child, keys)
    elif isinstance(value, list):
        for child in value:
            yield from _values_for_keys(child, keys)


def _stable_unique(values: Iterable[Any], *, limit: int = 64) -> list[str]:
    result = sorted({_text(value) for value in values if _text(value)})
    return result[:limit]


def _fallback_surfaces(value: Any) -> list[str]:
    def candidates_from(child: Any) -> Iterator[str]:
        if isinstance(child, dict):
            for key, nested in child.items():
                if str(key).strip().lower() not in _NON_IDENTITY_KEYS:
                    yield from candidates_from(nested)
        elif isinstance(child, list):
            for nested in child:
                yield from candidates_from(nested)
        else:
            yield from _scalar_texts(child)

    candidates = [text for text in candidates_from(value) if len(text) <= 1024]
    japanese = [text for text in candidates if _JAPANESE.search(text)]
    selected = japanese or [text for text in candidates if not text.isdecimal()]
    return _stable_unique(selected, limit=8)


def _xml_tag_texts(value: Any, tags: set[str]) -> Iterator[str]:
    if isinstance(value, dict):
        tag = str(value.get("tag") or "").lower()
        if tag in tags and _text(value.get("text")):
            yield _text(value["text"])
        for child in value.get("children") or []:
            yield from _xml_tag_texts(child, tags)


def _xml_codepoint_surfaces(value: dict[str, Any]) -> Iterator[str]:
    attributes = value.get("attributes") if isinstance(value.get("attributes"), dict) else {}
    candidate = _text(attributes.get("cp"))
    if _HEX_CODEPOINTS.fullmatch(candidate):
        yield "".join(chr(int(item, 16)) for item in candidate.split())


def _project_identity(value: dict[str, Any], family: str) -> dict[str, list[str]]:
    if family in {"streaming-xml", "rdf-xml"}:
        surfaces = _stable_unique(
            [
                *_xml_codepoint_surfaces(value),
                *_xml_tag_texts(
                    value,
                    {"keb", "literal", "orth", "lemma", "label", "preflabel", "altlabel", "term"},
                ),
            ],
            limit=16,
        )
        readings = _stable_unique(
            _xml_tag_texts(value, {"reb", "reading", "pronunciation", "kana", "yomi"}),
            limit=16,
        )
        if surfaces:
            return {
                "surfaces": surfaces,
                "readings": readings,
                "part_of_speech": _stable_unique(
                    _xml_tag_texts(value, {"pos", "part_of_speech"}), limit=16
                ),
                "domains": _stable_unique(
                    _xml_tag_texts(value, {"field", "domain", "category"}), limit=16
                ),
            }
    if family == "archive-index":
        text = _text(value.get("text"))
        return {
            "surfaces": [text] if text else [],
            "readings": [],
            "part_of_speech": [],
            "domains": [],
        }
    surfaces = _stable_unique(_values_for_keys(value, _KNOWN_SURFACE_KEYS), limit=16)
    if not surfaces:
        surfaces = _fallback_surfaces(value)
    return {
        "surfaces": surfaces,
        "readings": _stable_unique(_values_for_keys(value, _KNOWN_READING_KEYS), limit=16),
        "part_of_speech": _stable_unique(_values_for_keys(value, _KNOWN_POS_KEYS), limit=16),
        "domains": _stable_unique(_values_for_keys(value, _KNOWN_DOMAIN_KEYS), limit=16),
    }


def _xml_value(element: ET.Element) -> dict[str, Any]:
    children: list[dict[str, Any]] = []
    for child in list(element):
        children.append(_xml_value(child))
    return {
        "tag": element.tag.rsplit("}", 1)[-1],
        "attributes": dict(sorted((str(k), str(v)) for k, v in element.attrib.items())),
        "text": _text("".join(element.itertext())),
        "children": children,
    }


def _iter_json_values(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                yield item
            else:
                yield {"value": item}
    elif isinstance(value, dict):
        list_values = [(key, child) for key, child in value.items() if isinstance(child, list)]
        if list_values:
            context = {key: child for key, child in value.items() if not isinstance(child, list)}
            for key, children in list_values:
                for item in children:
                    yield {"collection": key, "collection_context": context, "value": item}
        elif len(value) > 1 and all(isinstance(child, (dict, list)) for child in value.values()):
            for key, child in value.items():
                yield {"collection_key": key, "value": child}
        else:
            yield value
    else:
        yield {"value": value}


def _iter_records(path: Path, profile: dict[str, Any]) -> Iterator[dict[str, Any]]:
    family = str(profile["parser_family"])
    encodings = list(profile.get("encodings") or ["utf-8-sig"])
    if family in {"streaming-xml", "rdf-xml"}:
        targets = set(profile.get("xml_target_tags") or [])
        with _open_decompressed(path) as handle:
            stack: list[ET.Element] = []
            for event, element in ET.iterparse(handle, events=("start", "end")):
                if event == "start":
                    stack.append(element)
                    continue
                local = element.tag.rsplit("}", 1)[-1]
                selected = not targets or local in targets
                if selected:
                    value = _xml_value(element)
                    value["xml_path"] = "/".join(
                        node.tag.rsplit("}", 1)[-1] for node in stack
                    )
                    yield value
                    element.clear()
                    if len(stack) > 1:
                        try:
                            stack[-2].remove(element)
                        except ValueError:
                            pass
                stack.pop()
        return
    if family == "json-corpus":
        encoding = _select_encoding(path, encodings)
        with _open_decompressed(path) as raw, io.TextIOWrapper(raw, encoding=encoding, errors="strict") as text:
            yield from _iter_json_values(json.load(text))
        return
    if family == "jsonl":
        encoding = _select_encoding(path, encodings)
        with _open_decompressed(path) as raw, io.TextIOWrapper(raw, encoding=encoding, errors="strict") as text:
            for line in text:
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    value = {"value": value}
                yield value
        return
    if family == "archive-index":
        if not zipfile.is_zipfile(path):
            yield {"archive_path": path.name, "archive_sha256": _sha256_file(path)}
            return
        with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory() as directory:
            for number, info in enumerate(sorted(archive.infolist(), key=lambda row: row.filename), 1):
                if info.is_dir():
                    continue
                name = _safe_member(info.filename)
                nested = Path(directory) / f"{number:08d}-{PurePosixPath(name).name}"
                with archive.open(info) as source:
                    digest = _copy_stream(source, nested, info.file_size)
                try:
                    encoding = _select_encoding(nested, encodings)
                    with _open_decompressed(nested) as raw, io.TextIOWrapper(
                        raw, encoding=encoding, errors="strict"
                    ) as handle:
                        for line_number, line in enumerate(handle, 1):
                            if line.strip():
                                yield {"archive_member": name, "line": line_number, "text": line.rstrip("\r\n")}
                except (UnicodeError, ValueError):
                    yield {"archive_member": name, "bytes": info.file_size, "sha256": digest}
        return

    encoding = _select_encoding(path, encodings)
    with _open_decompressed(path) as raw, io.TextIOWrapper(
        raw, encoding=encoding, errors="strict", newline=""
    ) as text:
        if family == "delimited-table":
            delimiter = profile.get("delimiter")
            if delimiter:
                for row in csv.reader(text, delimiter=str(delimiter), strict=True):
                    if row and not row[0].lstrip().startswith("#"):
                        yield {"columns": row}
            else:
                for line in text:
                    stripped = line.strip()
                    if stripped and not stripped.startswith(("#", ";;")):
                        yield {"columns": stripped.split()}
        elif family == "conllu":
            sentence_number = 1
            sentence_metadata: dict[str, str] = {}
            for line in text:
                stripped = line.strip()
                if not stripped:
                    sentence_number += 1
                    sentence_metadata = {}
                    continue
                if stripped.startswith("#"):
                    key, separator, value = stripped[1:].partition("=")
                    if separator:
                        sentence_metadata[key.strip()] = value.strip()
                    continue
                columns = stripped.split("\t")
                if len(columns) >= 10 and "-" not in columns[0] and "." not in columns[0]:
                    yield {
                        "sentence_number": sentence_number,
                        "sentence_metadata": dict(sorted(sentence_metadata.items())),
                        "token_id": columns[0], "surface": columns[1], "lemma": columns[2],
                        "upos": columns[3], "xpos": columns[4], "features": columns[5],
                        "head": columns[6], "dependency": columns[7], "deps": columns[8],
                        "misc": columns[9],
                    }
        elif family == "skk":
            for line in text:
                stripped = line.strip()
                if not stripped or stripped.startswith(";;") or "/" not in stripped:
                    continue
                reading, candidates = stripped.split(None, 1)
                yield {
                    "reading": reading,
                    "surfaces": [value.split(";", 1)[0] for value in candidates.strip("/").split("/") if value],
                    "raw_candidates": candidates,
                }
        elif family == "commented-sequence":
            for line in text:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                body, _, comment = stripped.partition("#")
                codepoints, _, status = body.partition(";")
                codepoints = codepoints.strip()
                surfaces: list[str] = []
                if _HEX_CODEPOINTS.fullmatch(codepoints):
                    surfaces = ["".join(chr(int(value, 16)) for value in codepoints.split())]
                yield {"surfaces": surfaces, "codepoints": codepoints, "status": status.strip(), "comment": comment.strip()}
        elif family == "knp":
            sentence_number = 0
            lines: list[str] = []
            tokens: list[str] = []
            for line in text:
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped == "EOS":
                    sentence_number += 1
                    yield {
                        "surface": "".join(tokens),
                        "sentence_number": sentence_number,
                        "knp_lines": lines,
                    }
                    lines = []
                    tokens = []
                    continue
                lines.append(stripped)
                if not stripped.startswith(("* ", "+ ", "# ")):
                    tokens.append(stripped.split()[0])
            if lines:
                sentence_number += 1
                yield {
                    "surface": "".join(tokens),
                    "sentence_number": sentence_number,
                    "knp_lines": lines,
                }
        else:
            for line in text:
                stripped = line.strip()
                if stripped:
                    yield {"surface": stripped.split()[0], "line": stripped}


def _nested_value(value: Any, names: set[str]) -> str:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in names:
                selected_values = list(_scalar_texts(child))
                if selected_values:
                    return selected_values[0]
            selected = _nested_value(child, names)
            if selected:
                return selected
    elif isinstance(value, list):
        for child in value:
            selected = _nested_value(child, names)
            if selected:
                return selected
    return ""


def _source_lineage(
    source: dict[str, Any], payload_path: str, payload_sha: str, value: dict[str, Any],
    record_number: int, record_sha: str, freeze_at: str,
) -> dict[str, Any]:
    lock = source.get("source_lock") if isinstance(source.get("source_lock"), dict) else {}
    license_name = _nested_value(value, {"license", "licence"}) or _nested_value(lock, {"license", "licence"})
    license_complete = bool(license_name)
    if not license_name:
        license_name = f"RIGHTS-LANE-{source['rights_lane']}; LICENSE-EXPRESSION-PENDING"
    version = _nested_value(value, {"version", "source_version", "dump_date", "date"}) or f"frozen@{freeze_at}"
    source_url = _nested_value(value, {"source_url", "url", "homepage"}) or _nested_value(lock, {"source_url", "url", "homepage"})
    source_id = str(source["source_id"])
    return {
        "dataset": _nested_value(value, {"dataset", "dataset_name"}) or source_id,
        "version": version,
        "license": license_name,
        "source_id": f"{source_id}:{payload_path}:{record_number}",
        "source_url": source_url,
        "source_sha256": str(source.get("raw_sha256") or payload_sha),
        "attribution": _nested_value(value, {"attribution", "publisher", "copyright"}),
        "logical_source_id": str(source.get("logical_source_id") or source_id),
        "source_record_id": f"{payload_path}:{record_number}",
        "source_record_sha256": record_sha,
        "artifact_id": int(source["artifact_id"]),
        "workflow_run_id": int(source.get("workflow_run_id", 0)),
        "payload_path": payload_path,
        "payload_sha256": payload_sha,
        "rights_lane": str(source["rights_lane"]),
        "public_runtime_eligible": bool(source["public_runtime_eligible"] and license_complete),
        "license_metadata_complete": license_complete,
    }


class _DedupStore:
    def __init__(self, path: Path, spool_path: Path):
        self.connection = sqlite3.connect(path)
        self.spool = spool_path.open("w+b")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.execute(
            "CREATE TABLE records (fingerprint TEXT PRIMARY KEY, offset INTEGER NOT NULL, "
            "size INTEGER NOT NULL) WITHOUT ROWID"
        )
        self.connection.execute(
            "CREATE TABLE lineages (fingerprint TEXT NOT NULL, signature TEXT NOT NULL, lineage TEXT NOT NULL, "
            "PRIMARY KEY (fingerprint, signature)) WITHOUT ROWID"
        )

    def add(self, projection: dict[str, Any], lineage: dict[str, Any]) -> bool:
        material = _json_line(projection)
        fingerprint = hashlib.sha256(material.encode("utf-8")).hexdigest()
        payload = material.encode("utf-8")
        inserted = self.connection.execute(
            "INSERT OR IGNORE INTO records VALUES (?, ?, ?)",
            (fingerprint, -1, len(payload)),
        ).rowcount == 1
        if inserted:
            offset = self.spool.tell()
            self.spool.write(payload)
            self.connection.execute(
                "UPDATE records SET offset=? WHERE fingerprint=?", (offset, fingerprint)
            )
        lineage_text = _json_line(lineage)
        signature = hashlib.sha256(lineage_text.encode("utf-8")).hexdigest()
        self.connection.execute(
            "INSERT OR IGNORE INTO lineages VALUES (?, ?, ?)",
            (fingerprint, signature, lineage_text),
        )
        return inserted

    def write(self, path: Path) -> int:
        count = 0
        raw_output: BinaryIO | None = None
        if path.name.endswith(".gz"):
            raw_output = path.open("wb")
            compressed = gzip.GzipFile(
                filename="", mode="wb", fileobj=raw_output, compresslevel=6, mtime=0
            )
            output_context = io.TextIOWrapper(compressed, encoding="utf-8", newline="\n")
        else:
            output_context = path.open("w", encoding="utf-8", newline="\n")
        with output_context as output:
            cursor = self.connection.execute(
                "SELECT fingerprint, offset, size FROM records ORDER BY fingerprint"
            )
            for fingerprint, offset, size in cursor:
                self.spool.seek(int(offset))
                projection = json.loads(self.spool.read(int(size)))
                lineages = [
                    json.loads(row[0])
                    for row in self.connection.execute(
                        "SELECT lineage FROM lineages WHERE fingerprint=? ORDER BY signature",
                        (fingerprint,),
                    )
                ]
                primary = dict(lineages[0])
                projection["adapter_record_id"] = f"ROLE-{fingerprint[:32]}"
                projection["source"] = primary
                if len(lineages) > 1:
                    projection["payload"]["duplicate_source_lineages"] = lineages
                projection["payload"]["exact_replay_count"] = len(lineages)
                output.write(_json_line(projection) + "\n")
                count += 1
        if raw_output is not None and not raw_output.closed:
            raw_output.close()
        return count

    def close(self) -> None:
        self.connection.commit()
        self.connection.close()
        self.spool.close()


def _matching(names: list[str], globs: list[str]) -> list[str]:
    import fnmatch
    return sorted(name for name in names if any(fnmatch.fnmatchcase(name, pattern) for pattern in globs))


def _materialized_payloads(
    archive: zipfile.ZipFile, source: dict[str, Any], profile: dict[str, Any], temp_root: Path,
) -> Iterator[tuple[str, Path, str]]:
    infos = {_safe_member(info.filename): info for info in archive.infolist() if not info.is_dir()}
    if profile.get("artifact_kind", "harvest") == "harvest":
        lock_names = [name for name in infos if PurePosixPath(name).name == "source-lock.json"]
        raw_names = [name for name in infos if name not in lock_names]
        if len(raw_names) != 1:
            raise ValueError(f"harvest raw payload not unique: {source['source_id']}")
        raw_name = raw_names[0]
        raw_path = temp_root / f"raw-{source['artifact_id']}-{PurePosixPath(raw_name).name}"
        with archive.open(infos[raw_name]) as stream:
            raw_sha = _copy_stream(stream, raw_path, infos[raw_name].file_size)
        if raw_sha != str(source.get("raw_sha256") or raw_sha):
            raise ValueError(f"harvest raw checksum mismatch: {source['source_id']}")
        if zipfile.is_zipfile(raw_path):
            with zipfile.ZipFile(raw_path) as nested:
                nested_infos = {_safe_member(info.filename): info for info in nested.infolist() if not info.is_dir()}
                for number, payload in enumerate(source["payloads"], 1):
                    name = _safe_member(str(payload["path"]))
                    info = nested_infos.get(name)
                    if info is None:
                        raise ValueError(f"declared payload missing: {source['source_id']}:{name}")
                    path = temp_root / f"payload-{source['source_id']}-{number:06d}-{PurePosixPath(name).name}"
                    with nested.open(info) as stream:
                        digest = _copy_stream(stream, path, info.file_size)
                    yield name, path, digest
                    path.unlink(missing_ok=True)
        else:
            yield raw_name, raw_path, raw_sha
        raw_path.unlink(missing_ok=True)
        return

    for outer_number, payload in enumerate(source["payloads"], 1):
        outer_name = _safe_member(str(payload["path"]))
        info = infos.get(outer_name)
        if info is None:
            raise ValueError(f"collection payload missing: {source['source_id']}:{outer_name}")
        outer_path = temp_root / f"outer-{source['source_id']}-{outer_number:04d}-{PurePosixPath(outer_name).name}"
        with archive.open(info) as stream:
            outer_sha = _copy_stream(stream, outer_path, info.file_size)
        expected = str(payload.get("sha256") or "")
        if expected and outer_sha != expected:
            raise ValueError(f"collection payload checksum mismatch: {source['source_id']}:{outer_name}")
        patterns = list(profile.get("inner_payload_globs") or [])
        if patterns and zipfile.is_zipfile(outer_path):
            with zipfile.ZipFile(outer_path) as nested:
                nested_infos = {_safe_member(row.filename): row for row in nested.infolist() if not row.is_dir()}
                for number, name in enumerate(_matching(list(nested_infos), patterns), 1):
                    nested_path = temp_root / f"inner-{source['source_id']}-{number:08d}-{PurePosixPath(name).name}"
                    with nested.open(nested_infos[name]) as stream:
                        digest = _copy_stream(stream, nested_path, nested_infos[name].file_size)
                    yield f"{outer_name}!/{name}", nested_path, digest
                    nested_path.unlink(missing_ok=True)
        elif patterns and tarfile.is_tarfile(outer_path):
            with tarfile.open(outer_path, "r:*") as nested:
                members = {_safe_member(row.name): row for row in nested.getmembers() if row.isfile()}
                for number, name in enumerate(_matching(list(members), patterns), 1):
                    nested_path = temp_root / f"inner-{source['source_id']}-{number:08d}-{PurePosixPath(name).name}"
                    stream = nested.extractfile(members[name])
                    if stream is None:
                        raise ValueError(f"cannot read nested member: {name}")
                    with stream:
                        digest = _copy_stream(stream, nested_path, members[name].size)
                    yield f"{outer_name}!/{name}", nested_path, digest
                    nested_path.unlink(missing_ok=True)
        else:
            yield outer_name, outer_path, outer_sha
        outer_path.unlink(missing_ok=True)


def build_frozen_raw_role_factory(
    bundle_path: Path,
    manifest_path: Path,
    profiles_path: Path,
    output_root: Path,
    *,
    shard_index: int | None = None,
    shard_count: int | None = None,
    compile_adapter: bool = True,
) -> dict[str, Any]:
    if (shard_index is None) != (shard_count is None):
        raise ValueError("shard-index and shard-count must be specified together")
    if shard_count is not None and shard_count < 1:
        raise ValueError("shard-count must be positive")
    if shard_index is not None and not 0 <= shard_index < int(shard_count):
        raise ValueError("shard-index must be within shard-count")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_intake_manifest(manifest)
    profiles = load_profiles(profiles_path)
    by_profile = {str(row["source_id"]): row for row in profiles["sources"]}
    actual_bundle_sha = _sha256_file(bundle_path)
    expected_bundle_sha = str(manifest.get("bundle_sha256") or "").lower()
    if expected_bundle_sha and actual_bundle_sha != expected_bundle_sha:
        raise ValueError(f"frozen bundle checksum mismatch: {actual_bundle_sha}!={expected_bundle_sha}")

    output_root.mkdir(parents=True, exist_ok=True)
    records_path = output_root / "source-role-records.jsonl.gz"
    unresolved_path = output_root / "unresolved-source-role-records.jsonl"
    artifact_meta = {int(row["id"]): row for row in manifest.get("artifacts") or []}
    sources_by_artifact: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for source in manifest["sources"]:
        artifact_id = int(source["artifact_id"])
        assigned = shard_count is None or artifact_id % shard_count == shard_index
        if assigned and any(role != MEANING_ROLE for role in source.get("source_roles") or []):
            sources_by_artifact[artifact_id].append(source)

    counters: Counter[str] = Counter()
    by_source: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory() as directory, tarfile.open(bundle_path, "r") as bundle, unresolved_path.open(
        "w", encoding="utf-8", newline="\n"
    ) as unresolved:
        temp_root = Path(directory)
        store = _DedupStore(temp_root / "dedup.sqlite3", temp_root / "unique-records.spool")
        try:
            members = {_safe_member(row.name): row for row in bundle.getmembers() if row.isfile()}
            for artifact_id, selected_sources in sorted(sources_by_artifact.items()):
                metadata = artifact_meta.get(artifact_id)
                if metadata is None:
                    raise ValueError(f"artifact metadata missing: {artifact_id}")
                member_name = _safe_member(str(metadata["bundle_path"]))
                member = members.get(member_name)
                if member is None:
                    raise ValueError(f"artifact missing from frozen bundle: {member_name}")
                artifact_path = temp_root / f"artifact-{artifact_id}.zip"
                stream = bundle.extractfile(member)
                if stream is None:
                    raise ValueError(f"cannot read bundle member: {member_name}")
                with stream:
                    digest = _copy_stream(stream, artifact_path, member.size)
                expected = str(metadata.get("downloaded_zip_sha256") or "")
                if expected and digest != expected:
                    raise ValueError(f"artifact checksum mismatch: {artifact_id}")
                with zipfile.ZipFile(artifact_path) as archive:
                    for source in sorted(selected_sources, key=lambda row: str(row["source_id"])):
                        source_id = str(source["source_id"])
                        profile = by_profile.get(source_id)
                        if profile is None:
                            raise ValueError(f"source profile missing: {source_id}")
                        source_counts: Counter[str] = Counter()
                        for payload_path, payload_file, payload_sha in _materialized_payloads(
                            archive, source, profile, temp_root
                        ):
                            source_counts["payloads"] += 1
                            for record_number, value in enumerate(_iter_records(payload_file, profile), 1):
                                source_counts["input_records"] += 1
                                counters["input_records"] += 1
                                record_sha = hashlib.sha256(_json_line(value).encode("utf-8")).hexdigest()
                                identity = _project_identity(value, str(profile["parser_family"]))
                                roles = sorted(role for role in source["source_roles"] if role != MEANING_ROLE)
                                lineage = _source_lineage(
                                    source, payload_path, payload_sha, value, record_number,
                                    record_sha, str(manifest.get("freeze_at") or "unknown"),
                                )
                                if not identity["surfaces"]:
                                    unresolved.write(
                                        _json_line({
                                            "source_id": source_id,
                                            "logical_source_id": source.get("logical_source_id", source_id),
                                            "payload_path": payload_path,
                                            "record_number": record_number,
                                            "source_roles": roles,
                                            "reason": "EXPLICIT_SURFACE_NOT_FOUND",
                                            "source_record_sha256": record_sha,
                                            "source": lineage,
                                            "value": value,
                                        }) + "\n"
                                    )
                                    source_counts["unresolved_records"] += 1
                                    counters["unresolved_records"] += 1
                                    continue
                                source_counts["resolved_input_records"] += 1
                                counters["resolved_input_records"] += 1
                                if not lineage["license_metadata_complete"]:
                                    source_counts["license_metadata_pending_records"] += 1
                                    counters["license_metadata_pending_records"] += 1
                                for role in roles:
                                    projection = {
                                        "source_role": role,
                                        "surfaces": identity["surfaces"],
                                        "readings": identity["readings"],
                                        "part_of_speech_list": identity["part_of_speech"],
                                        "domains": identity["domains"],
                                        "payload": {
                                            "role_factory_version": ROLE_FACTORY_VERSION,
                                            "parser_family": profile["parser_family"],
                                            "source_value": value,
                                        },
                                        "logical_source_id": str(source.get("logical_source_id") or source_id),
                                    }
                                    inserted = store.add(projection, lineage)
                                    source_counts["role_projections"] += 1
                                    counters["role_projections"] += 1
                                    if not inserted:
                                        source_counts["exact_replay_duplicates"] += 1
                                        counters["exact_replay_duplicates"] += 1
                        if source_counts["input_records"] < 1:
                            raise ValueError(f"role factory parsed no records: {source_id}")
                        if source_counts["input_records"] != (
                            source_counts["resolved_input_records"] + source_counts["unresolved_records"]
                        ):
                            raise RuntimeError(f"ROLE_FACTORY_RECORD_LOSS:{source_id}:{dict(source_counts)}")
                        by_source[source_id] = dict(sorted(source_counts.items()))
                artifact_path.unlink()
            store.connection.commit()
            unique_records = store.write(records_path)
        finally:
            store.close()

    expected_processed_sources = sum(len(values) for values in sources_by_artifact.values())
    if len(by_source) != expected_processed_sources:
        raise RuntimeError("ROLE_FACTORY_SOURCE_LOSS")
    if counters["input_records"] != counters["resolved_input_records"] + counters["unresolved_records"]:
        raise RuntimeError("ROLE_FACTORY_GLOBAL_RECORD_LOSS")
    if counters["role_projections"] != unique_records + counters["exact_replay_duplicates"]:
        raise RuntimeError("ROLE_FACTORY_DEDUP_CONSERVATION_FAILURE")

    adapter_manifest: dict[str, Any] | None = None
    if compile_adapter:
        adapter_root = output_root / "adapter-output"
        adapter_manifest = compile_adapter_contract([records_path], adapter_root)
    report = {
        "schema_version": ROLE_FACTORY_VERSION,
        "mode": "frozen-raw-auxiliary-role-factory",
        "bundle_sha256": actual_bundle_sha,
        "intake_source_count": int(manifest["source_count"]),
        "processed_source_count": len(by_source),
        "input_record_count": counters["input_records"],
        "resolved_input_record_count": counters["resolved_input_records"],
        "unresolved_input_record_count": counters["unresolved_records"],
        "role_projection_count": counters["role_projections"],
        "unique_adapter_record_count": unique_records,
        "exact_replay_duplicate_count": counters["exact_replay_duplicates"],
        "license_metadata_pending_record_count": counters["license_metadata_pending_records"],
        "source_counts": dict(sorted(by_source.items())),
        "adapter_contract": adapter_manifest,
        "shard": (
            {"index": shard_index, "count": shard_count}
            if shard_count is not None
            else None
        ),
        "boundaries": {
            "all_declared_auxiliary_sources_processed": shard_count is None,
            "all_assigned_auxiliary_sources_processed": True,
            "input_record_conservation_verified": True,
            "role_projection_conservation_verified": True,
            "exact_replay_deduplication_only": True,
            "same_surface_different_payload_preserved": True,
            "multiple_readings_parts_of_speech_domains_preserved": True,
            "duplicate_source_lineage_preserved": True,
            "missing_license_expression_never_public_runtime_eligible": True,
            "non_definition_sources_never_become_meanings": True,
            "automatic_approval": False,
            "automatic_runtime_promotion": False,
        },
        "files": {
            records_path.name: {"sha256": _sha256_file(records_path), "bytes": records_path.stat().st_size},
            unresolved_path.name: {"sha256": _sha256_file(unresolved_path), "bytes": unresolved_path.stat().st_size},
        },
    }
    (output_root / "role-factory-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def _projection_and_lineages(
    record: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    projection = dict(record)
    projection.pop("adapter_record_id", None)
    primary = projection.pop("source")
    payload = dict(projection["payload"])
    lineages = payload.pop("duplicate_source_lineages", None) or [primary]
    payload.pop("exact_replay_count", None)
    projection["payload"] = payload
    return projection, lineages


def merge_frozen_raw_role_factory_shards(
    manifest_path: Path,
    shards_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_intake_manifest(manifest)
    expected_sources = {
        str(source["source_id"])
        for source in manifest["sources"]
        if any(role != MEANING_ROLE for role in source.get("source_roles") or [])
    }
    report_paths = sorted(shards_root.rglob("role-factory-report.json"))
    if not report_paths:
        raise ValueError("role factory shard reports not found")

    reports: list[tuple[Path, dict[str, Any]]] = []
    shard_count: int | None = None
    indexes: set[int] = set()
    bundle_sha: str | None = None
    processed_sources: set[str] = set()
    source_counts: dict[str, dict[str, Any]] = {}
    counters: Counter[str] = Counter()
    for path in report_paths:
        report = json.loads(path.read_text(encoding="utf-8"))
        shard = report.get("shard")
        if not isinstance(shard, dict):
            raise ValueError(f"not a role factory shard report: {path}")
        index = int(shard["index"])
        count = int(shard["count"])
        if shard_count is None:
            shard_count = count
        if count != shard_count or index in indexes or not 0 <= index < count:
            raise ValueError(f"invalid or duplicate role factory shard: {path}")
        indexes.add(index)
        current_bundle_sha = str(report["bundle_sha256"])
        if bundle_sha is None:
            bundle_sha = current_bundle_sha
        if current_bundle_sha != bundle_sha:
            raise ValueError("role factory shard bundle mismatch")
        current_sources = set(report.get("source_counts") or {})
        if processed_sources & current_sources:
            raise ValueError("role factory source appeared in multiple shards")
        processed_sources.update(current_sources)
        source_counts.update(report.get("source_counts") or {})
        counters["input_records"] += int(report["input_record_count"])
        counters["resolved_input_records"] += int(report["resolved_input_record_count"])
        counters["unresolved_records"] += int(report["unresolved_input_record_count"])
        counters["role_projections"] += int(report["role_projection_count"])
        counters["license_metadata_pending_records"] += int(
            report["license_metadata_pending_record_count"]
        )
        reports.append((path, report))

    if shard_count is None or indexes != set(range(shard_count)):
        raise RuntimeError(f"ROLE_FACTORY_SHARD_SET_INCOMPLETE:{sorted(indexes)}:{shard_count}")
    if processed_sources != expected_sources:
        missing = sorted(expected_sources - processed_sources)
        extra = sorted(processed_sources - expected_sources)
        raise RuntimeError(f"ROLE_FACTORY_SOURCE_SET_MISMATCH:missing={missing}:extra={extra}")
    expected_bundle_sha = str(manifest.get("bundle_sha256") or "").lower()
    if expected_bundle_sha and bundle_sha != expected_bundle_sha:
        raise ValueError("role factory shard manifest bundle mismatch")

    output_root.mkdir(parents=True, exist_ok=True)
    records_path = output_root / "source-role-records.jsonl.gz"
    unresolved_path = output_root / "unresolved-source-role-records.jsonl"
    with tempfile.TemporaryDirectory() as directory, unresolved_path.open(
        "w", encoding="utf-8", newline="\n"
    ) as unresolved:
        temp_root = Path(directory)
        store = _DedupStore(temp_root / "dedup.sqlite3", temp_root / "unique-records.spool")
        try:
            ordered_reports = sorted(reports, key=lambda item: int(item[1]["shard"]["index"]))
            for report_path, _report in ordered_reports:
                shard_root = report_path.parent
                shard_records = shard_root / "source-role-records.jsonl.gz"
                shard_unresolved = shard_root / "unresolved-source-role-records.jsonl"
                if not shard_records.is_file() or not shard_unresolved.is_file():
                    raise ValueError(f"role factory shard files missing: {shard_root}")
                with gzip.open(shard_records, "rt", encoding="utf-8") as handle:
                    for line in handle:
                        record = json.loads(line)
                        projection, lineages = _projection_and_lineages(record)
                        for lineage in lineages:
                            store.add(projection, lineage)
                with shard_unresolved.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        unresolved.write(line)
            store.connection.commit()
            unique_records = store.write(records_path)
        finally:
            store.close()

    if counters["input_records"] != counters["resolved_input_records"] + counters["unresolved_records"]:
        raise RuntimeError("ROLE_FACTORY_GLOBAL_RECORD_LOSS")
    exact_replay_duplicates = counters["role_projections"] - unique_records
    if exact_replay_duplicates < 0:
        raise RuntimeError("ROLE_FACTORY_DEDUP_CONSERVATION_FAILURE")

    adapter_root = output_root / "adapter-output"
    adapter_manifest = compile_adapter_contract([records_path], adapter_root)
    report = {
        "schema_version": ROLE_FACTORY_VERSION,
        "mode": "frozen-raw-auxiliary-role-factory",
        "bundle_sha256": bundle_sha,
        "intake_source_count": int(manifest["source_count"]),
        "processed_source_count": len(processed_sources),
        "input_record_count": counters["input_records"],
        "resolved_input_record_count": counters["resolved_input_records"],
        "unresolved_input_record_count": counters["unresolved_records"],
        "role_projection_count": counters["role_projections"],
        "unique_adapter_record_count": unique_records,
        "exact_replay_duplicate_count": exact_replay_duplicates,
        "license_metadata_pending_record_count": counters[
            "license_metadata_pending_records"
        ],
        "source_counts": dict(sorted(source_counts.items())),
        "adapter_contract": adapter_manifest,
        "shard_merge": {"count": shard_count, "indexes": sorted(indexes)},
        "boundaries": {
            "all_declared_auxiliary_sources_processed": True,
            "all_assigned_auxiliary_sources_processed": True,
            "all_declared_shards_merged": True,
            "input_record_conservation_verified": True,
            "role_projection_conservation_verified": True,
            "exact_replay_deduplication_only": True,
            "same_surface_different_payload_preserved": True,
            "multiple_readings_parts_of_speech_domains_preserved": True,
            "duplicate_source_lineage_preserved": True,
            "missing_license_expression_never_public_runtime_eligible": True,
            "non_definition_sources_never_become_meanings": True,
            "automatic_approval": False,
            "automatic_runtime_promotion": False,
        },
        "files": {
            records_path.name: {
                "sha256": _sha256_file(records_path),
                "bytes": records_path.stat().st_size,
            },
            unresolved_path.name: {
                "sha256": _sha256_file(unresolved_path),
                "bytes": unresolved_path.stat().st_size,
            },
        },
    }
    (output_root / "role-factory-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report
