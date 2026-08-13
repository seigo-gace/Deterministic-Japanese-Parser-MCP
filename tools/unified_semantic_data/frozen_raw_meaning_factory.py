"""Convert frozen lexical-definition payloads into deterministic adapter records.

This is the missing middle stage between the immutable raw intake and the semantic
review factory.  It only copies source-authored definitions from payloads that the
intake manifest explicitly classified as ``lexical-definition``.  It never invents,
translates, approves, or promotes a meaning.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
import tempfile
from typing import Any, BinaryIO
import unicodedata
import zipfile

from .raw_intake import validate_intake_manifest
from .semantic_labeler import candidate_has_real_meaning
from .source_adapter_contract import compile_adapter_contract


MEANING_FACTORY_VERSION = "1.0.0"
MEANING_ROLE = "lexical-definition"


def _text(value: Any) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    return [value]


def _stable_unique(values: Iterable[Any]) -> list[str]:
    return sorted({_text(value) for value in values if _text(value)})


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
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe archive path: {name}")
    return str(path)


def _nested_texts(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        if _text(value):
            yield _text(value)
    elif isinstance(value, list):
        for item in value:
            yield from _nested_texts(item)
    elif isinstance(value, dict):
        for key in ("text", "meaning", "gloss", "definition", "value"):
            if key in value:
                yield from _nested_texts(value[key])


def _field_texts(row: dict[str, Any], *names: str) -> list[str]:
    return _stable_unique(
        text
        for name in names
        for text in _nested_texts(row.get(name))
    )


def _source_value(row: dict[str, Any], *names: str) -> str:
    nested = row.get("source") if isinstance(row.get("source"), dict) else {}
    for name in names:
        value = row.get(name)
        if _text(value):
            return _text(value)
        value = nested.get(name)
        if _text(value):
            return _text(value)
    return ""


def _extract_fields(source_id: str, row: dict[str, Any]) -> dict[str, list[str]]:
    surfaces = _field_texts(
        row, "surface", "surfaces", "lemma", "word", "title", "headword"
    )
    readings = _field_texts(
        row, "reading", "readings", "pronunciation", "pronunciations"
    )
    meanings = _field_texts(
        row, "meaning", "meanings", "gloss", "glosses", "definition", "definitions"
    )

    if source_id == "ninjal-hatoma-tei-lex0-20260428":
        forms = row.get("forms") if isinstance(row.get("forms"), list) else []
        readings = _stable_unique(
            [*readings, *(
                text
                for form in forms
                if isinstance(form, dict)
                for text in _nested_texts(form.get("pronunciations"))
            )]
        )
    elif source_id == "j-ono-definitions":
        surfaces = _stable_unique(
            [
                *surfaces,
                row.get("hiragana"),
                row.get("katakana"),
                row.get("romaji"),
            ]
        )
        resolved = row.get("resolved_meaning_evidence")
        meanings = _stable_unique([*meanings, *_nested_texts(resolved)])

    return {
        "surfaces": surfaces,
        "readings": readings,
        "part_of_speech": _field_texts(
            row, "part_of_speech", "part_of_speech_list", "pos", "pos_title",
            "grammatical_labels",
        ),
        "domains": _field_texts(row, "domains", "domain", "categories", "category"),
        "meanings": meanings,
    }


def _adapter_row(
    row: dict[str, Any],
    *,
    source: dict[str, Any],
    payload: dict[str, Any],
    line_number: int,
    freeze_at: str,
) -> dict[str, Any]:
    source_id = str(source["source_id"])
    fields = _extract_fields(source_id, row)
    row_id = _source_value(row, "record_id", "id", "entry_id", "source_id")
    row_bytes = _json_line(row).encode("utf-8")
    row_sha = hashlib.sha256(row_bytes).hexdigest()
    adapter_id = f"FROZEN-{source_id}-{row_sha[:24]}"
    if not fields["surfaces"]:
        raise ValueError(
            f"MEANING_SURFACE_REQUIRED:{source_id}:{payload['path']}:{line_number}"
        )
    if not candidate_has_real_meaning({"glosses": fields["meanings"]}):
        raise ValueError(
            f"SOURCE_AUTHORED_MEANING_REQUIRED:{source_id}:{payload['path']}:{line_number}"
        )

    nested_source = row.get("source") if isinstance(row.get("source"), dict) else {}
    upstream_sha = _source_value(
        row, "source_sha256", "source_archive_sha256", "source_xml_sha256",
        "data_sha256",
    )
    license_name = _source_value(row, "license")
    if not license_name:
        raise ValueError(
            f"SOURCE_LICENSE_REQUIRED:{source_id}:{payload['path']}:{line_number}"
        )
    version = _source_value(
        row, "version", "source_version", "dump_date", "extraction_date",
        "upstream_commit", "tei_edition",
    ) or f"frozen@{freeze_at}"
    source_url = _source_value(
        row, "source_url", "source_page_url", "official_dataset_page",
        "upstream_repository", "repository", "data_url", "homepage",
    )
    attribution = _source_value(row, "attribution", "copyright", "publisher")

    return {
        "adapter_record_id": adapter_id,
        "source_role": MEANING_ROLE,
        "surfaces": fields["surfaces"],
        "readings": fields["readings"],
        "part_of_speech_list": fields["part_of_speech"],
        "domains": fields["domains"],
        "meanings": fields["meanings"],
        "source": {
            "dataset": _source_value(row, "dataset") or source_id,
            "version": version,
            "license": license_name,
            "source_id": f"{source_id}:{row_id or line_number}",
            "source_url": source_url,
            "source_sha256": upstream_sha or str(payload["sha256"]),
            "attribution": attribution,
            "logical_source_id": source.get("logical_source_id", source_id),
            "source_record_id": row_id or f"{payload['path']}:{line_number}",
            "source_record_sha256": _source_value(row, "source_record_sha256") or row_sha,
            "artifact_id": int(source["artifact_id"]),
            "workflow_run_id": int(source.get("workflow_run_id", 0)),
            "payload_path": str(payload["path"]),
            "payload_sha256": str(payload["sha256"]),
            "rights_lane": str(source["rights_lane"]),
            "public_runtime_eligible": bool(source["public_runtime_eligible"]),
            "source_meaning_complete": bool(row.get("meaning_complete", True)),
        },
        "payload": {
            "source_fields_preserved": sorted(nested_source),
            "meaning_factory_version": MEANING_FACTORY_VERSION,
        },
    }


def _copy_stream(source: BinaryIO, destination: Path, *, expected_bytes: int) -> str:
    digest = hashlib.sha256()
    size = 0
    with destination.open("wb") as output:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            size += len(chunk)
            if size > expected_bytes:
                raise ValueError(f"archive member exceeds declared bytes: {destination.name}")
            digest.update(chunk)
            output.write(chunk)
    if size != expected_bytes:
        raise ValueError(
            f"archive member byte mismatch: {destination.name}:{size}!={expected_bytes}"
        )
    return digest.hexdigest()


def _iter_payload_rows(path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    opener = gzip.open if path.name.endswith(".gz") else Path.open
    with opener(path, "rt", encoding="utf-8") as handle:  # type: ignore[arg-type]
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"JSONL row must be object: {path}:{line_number}")
            yield line_number, value


def _artifact_by_id(manifest: dict[str, Any]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for artifact in manifest.get("artifacts") or []:
        artifact_id = int(artifact["id"])
        if artifact_id in result:
            raise ValueError(f"duplicate artifact id in bundle manifest: {artifact_id}")
        result[artifact_id] = artifact
    return result


def build_frozen_raw_meaning_factory(
    bundle_path: Path,
    manifest_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    """Extract every declared lexical-definition payload and compile adapter lanes."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_intake_manifest(manifest)
    expected_bundle_sha = _text(manifest.get("bundle_sha256")).lower()
    actual_bundle_sha = _sha256_file(bundle_path)
    if expected_bundle_sha and actual_bundle_sha != expected_bundle_sha:
        raise ValueError(
            f"frozen bundle checksum mismatch: {actual_bundle_sha}!={expected_bundle_sha}"
        )

    definition_sources = [
        source
        for source in manifest["sources"]
        if MEANING_ROLE in (source.get("source_roles") or [])
    ]
    if not definition_sources:
        raise ValueError("frozen intake contains no lexical-definition sources")
    for source in definition_sources:
        if source.get("parser_family") != "jsonl":
            raise ValueError(
                f"unsupported lexical-definition parser family: "
                f"{source['source_id']}:{source.get('parser_family')}"
            )

    output_root.mkdir(parents=True, exist_ok=True)
    adapter_path = output_root / "source-adapter-records.jsonl"
    unresolved_path = output_root / "unresolved-meaning-records.jsonl"
    artifacts = _artifact_by_id(manifest)
    sources_by_artifact: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for source in definition_sources:
        sources_by_artifact[int(source["artifact_id"])].append(source)

    counts: Counter[str] = Counter()
    by_source: dict[str, dict[str, Any]] = {}
    with (
        tarfile.open(bundle_path, "r") as bundle,
        adapter_path.open("w", encoding="utf-8", newline="\n") as adapter_output,
        unresolved_path.open("w", encoding="utf-8", newline="\n") as unresolved_output,
        tempfile.TemporaryDirectory() as directory,
    ):
        bundle_members = {
            _safe_member(member.name): member
            for member in bundle.getmembers()
            if member.isfile()
        }
        temp_root = Path(directory)
        for artifact_id, selected_sources in sorted(sources_by_artifact.items()):
            artifact = artifacts.get(artifact_id)
            if artifact is None:
                raise ValueError(f"artifact metadata missing: {artifact_id}")
            bundle_member = _safe_member(str(artifact["bundle_path"]))
            member = bundle_members.get(bundle_member)
            if member is None:
                raise ValueError(f"artifact missing from frozen bundle: {bundle_member}")
            artifact_path = temp_root / f"{artifact_id}.zip"
            stream = bundle.extractfile(member)
            if stream is None:
                raise ValueError(f"cannot read frozen artifact: {bundle_member}")
            with stream:
                digest = _copy_stream(stream, artifact_path, expected_bytes=int(member.size))
            expected = _text(artifact.get("downloaded_zip_sha256")).lower()
            if expected and digest != expected:
                raise ValueError(f"artifact checksum mismatch: {artifact_id}")

            with zipfile.ZipFile(artifact_path) as archive:
                members = {
                    _safe_member(info.filename): info
                    for info in archive.infolist()
                    if not info.is_dir()
                }
                for source in sorted(selected_sources, key=lambda item: item["source_id"]):
                    source_count = 0
                    payload_count = 0
                    for payload_index, payload in enumerate(source["payloads"], 1):
                        payload_name = _safe_member(str(payload["path"]))
                        info = members.get(payload_name)
                        if info is None:
                            raise ValueError(
                                f"declared meaning payload missing: {source['source_id']}:{payload_name}"
                            )
                        payload_path = temp_root / (
                            f"{artifact_id}-{source['source_id']}-{payload_index:03d}"
                            + (".jsonl.gz" if payload_name.endswith(".gz") else ".jsonl")
                        )
                        with archive.open(info) as stream:
                            payload_sha = _copy_stream(
                                stream, payload_path, expected_bytes=int(info.file_size)
                            )
                        expected_payload_sha = _text(payload.get("sha256")).lower()
                        if expected_payload_sha and payload_sha != expected_payload_sha:
                            raise ValueError(
                                f"meaning payload checksum mismatch: {source['source_id']}:{payload_name}"
                            )
                        payload_meta = {**payload, "sha256": payload_sha}
                        payload_count += 1
                        for line_number, row in _iter_payload_rows(payload_path):
                            try:
                                adapter_row = _adapter_row(
                                    row,
                                    source=source,
                                    payload=payload_meta,
                                    line_number=line_number,
                                    freeze_at=str(manifest.get("freeze_at") or "unknown"),
                                )
                            except ValueError as exc:
                                unresolved_output.write(
                                    _json_line(
                                        {
                                            "source_id": source["source_id"],
                                            "payload_path": payload_name,
                                            "line": line_number,
                                            "reason": str(exc),
                                        }
                                    )
                                    + "\n"
                                )
                                counts["unresolved_records"] += 1
                                continue
                            adapter_output.write(_json_line(adapter_row) + "\n")
                            counts["adapter_records"] += 1
                            source_count += 1
                        payload_path.unlink()
                    by_source[str(source["source_id"])] = {
                        "adapter_records": source_count,
                        "payload_count": payload_count,
                        "rights_lane": source["rights_lane"],
                        "public_runtime_eligible": source["public_runtime_eligible"],
                    }
            artifact_path.unlink()

    if counts["unresolved_records"]:
        raise RuntimeError(
            "FROZEN_MEANING_FACTORY_INCOMPLETE: "
            f"unresolved_records={counts['unresolved_records']}; "
            f"inspect {unresolved_path.name}"
        )
    empty_sources = [
        source_id
        for source_id, values in by_source.items()
        if int(values["adapter_records"]) < 1
    ]
    if empty_sources:
        raise ValueError(
            f"lexical-definition sources produced no meanings: {empty_sources}"
        )

    adapter_root = output_root / "adapter-output"
    adapter_manifest = compile_adapter_contract([adapter_path], adapter_root)
    report = {
        "schema_version": MEANING_FACTORY_VERSION,
        "mode": "frozen-raw-source-authored-meaning-factory",
        "bundle_sha256": actual_bundle_sha,
        "intake_source_count": int(manifest["source_count"]),
        "lexical_definition_source_count": len(definition_sources),
        "non_definition_source_count": int(manifest["source_count"]) - len(definition_sources),
        "adapter_record_count": counts["adapter_records"],
        "unresolved_record_count": counts["unresolved_records"],
        "source_counts": dict(sorted(by_source.items())),
        "adapter_contract": adapter_manifest,
        "files": {
            "source_adapter_records": {
                "path": adapter_path.name,
                "sha256": _sha256_file(adapter_path),
                "bytes": adapter_path.stat().st_size,
            },
            "unresolved": {
                "path": unresolved_path.name,
                "sha256": _sha256_file(unresolved_path),
                "bytes": unresolved_path.stat().st_size,
            },
        },
        "boundaries": {
            "all_declared_lexical_definition_sources_processed": True,
            "source_authored_meanings_only": True,
            "placeholder_meanings_rejected": True,
            "payload_and_artifact_checksums_verified": True,
            "source_rights_and_lineage_preserved": True,
            "automatic_definition_generation": False,
            "automatic_approval": False,
            "automatic_runtime_promotion": False,
            "decision_ledger_required": True,
            "non_definition_sources_do_not_become_meanings": True,
        },
    }
    (output_root / "meaning-factory-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report
