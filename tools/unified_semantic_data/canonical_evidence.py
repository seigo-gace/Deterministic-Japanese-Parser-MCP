"""Deterministically attach non-definition source evidence to canonical dictionary records.

Many useful Japanese resources are not dictionaries of natural-language definitions.
They provide classifications, translations, familiarity, frequency, entity types,
sentiment, usage, syntax, orthography, or educational metadata. This stage preserves
those resources as auxiliary evidence and attaches them only when lexical identity can
be resolved without guessing. It never converts auxiliary evidence into a meaning.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import gzip
import json
from pathlib import Path
import shutil
from typing import Any, Iterable, Iterator

from .canonical_dictionary import validate_compiled_dictionary_root
from .common import _json_line, _sha256_bytes, _sha256_file, normalize_key

CANONICAL_EVIDENCE_SCHEMA_VERSION = "1.0.0"
ALLOWED_SOURCE_ROLES = {
    "domain-term",
    "education",
    "entity",
    "error-normalization",
    "familiarity",
    "frequency",
    "knowledge-relation",
    "lexical-relation",
    "morphology",
    "orthography",
    "pragmatics",
    "pronunciation",
    "semantic-class",
    "sentiment",
    "syntax",
    "temporal",
    "translation",
    "usage",
}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    return [value]


def _stable_unique(values: Iterable[Any]) -> list[str]:
    return sorted({str(value or "").strip() for value in values if str(value or "").strip()})


def _iter_dictionary_records(root: Path) -> Iterator[dict[str, Any]]:
    manifest = validate_compiled_dictionary_root(root)
    for shard in range(int(manifest.get("record_shards", 0))):
        path = root / "records" / f"dictionary-{shard:04d}.jsonl.gz"
        if not path.is_file():
            raise FileNotFoundError(path)
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(
                        f"canonical dictionary row must be object: {path}:{line_number}"
                    )
                yield value


def _iter_evidence_paths(roots: Iterable[Path]) -> Iterator[Path]:
    paths: list[Path] = []
    for root in roots:
        if root.is_file() and (
            root.suffix == ".jsonl" or root.name.endswith(".jsonl.gz")
        ):
            paths.append(root)
        elif root.is_dir():
            paths.extend(sorted(root.rglob("*.jsonl"), key=str))
            paths.extend(sorted(root.rglob("*.jsonl.gz"), key=str))
    for path in sorted(set(paths), key=str):
        yield path


def _validate_source(source: dict[str, Any], evidence_id: str) -> dict[str, Any]:
    required = ("dataset", "version", "license", "source_id", "source_sha256")
    missing = [key for key in required if not str(source.get(key) or "").strip()]
    if missing:
        raise ValueError(
            f"canonical evidence source fields required for {evidence_id}: {missing}"
        )
    digest = str(source.get("source_sha256") or "").strip()
    if len(digest) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in digest):
        raise ValueError(f"canonical evidence source_sha256 invalid: {evidence_id}")
    normalized = {
        "dataset": str(source.get("dataset") or "").strip(),
        "version": str(source.get("version") or "").strip(),
        "license": str(source.get("license") or "").strip(),
        "source_id": str(source.get("source_id") or "").strip(),
        "source_url": str(source.get("source_url") or "").strip(),
        "source_sha256": digest.lower(),
        "attribution": str(source.get("attribution") or "").strip(),
    }
    for key in (
        "logical_source_id",
        "source_record_id",
        "source_record_sha256",
        "payload_path",
        "payload_sha256",
        "rights_lane",
    ):
        value = str(source.get(key) or "").strip()
        if value:
            normalized[key] = value
    for key in ("artifact_id", "workflow_run_id"):
        value = source.get(key)
        if value not in (None, ""):
            normalized[key] = int(value)
    for key in ("public_runtime_eligible", "license_metadata_complete"):
        if key in source:
            normalized[key] = bool(source.get(key))
    for key in ("source_record_sha256", "payload_sha256"):
        if key in normalized:
            value = str(normalized[key]).lower()
            if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise ValueError(f"canonical evidence {key} invalid: {evidence_id}")
            normalized[key] = value
    return normalized


def normalize_evidence_record(raw: dict[str, Any], *, path: Path, line: int) -> dict[str, Any]:
    evidence_id = str(raw.get("evidence_id") or raw.get("id") or "").strip()
    if not evidence_id:
        raise ValueError(f"canonical evidence id required: {path}:{line}")
    role = str(raw.get("source_role") or raw.get("role") or "").strip()
    if role not in ALLOWED_SOURCE_ROLES:
        raise ValueError(f"canonical evidence source_role invalid: {evidence_id}:{role}")
    surfaces = _stable_unique(
        [
            raw.get("surface"),
            raw.get("lemma"),
            *_as_list(raw.get("surfaces")),
        ]
    )
    if not surfaces:
        raise ValueError(f"canonical evidence surface required: {evidence_id}")
    readings = _stable_unique(
        normalize_key(value)
        for value in [raw.get("reading"), *_as_list(raw.get("readings"))]
    )
    pos = _stable_unique(
        normalize_key(value)
        for value in [
            raw.get("part_of_speech"),
            raw.get("pos"),
            *_as_list(raw.get("part_of_speech_list")),
        ]
    )
    payload = raw.get("payload")
    if not isinstance(payload, dict) or not payload:
        raise ValueError(f"canonical evidence payload object required: {evidence_id}")
    source = raw.get("source") or {}
    if not isinstance(source, dict):
        raise ValueError(f"canonical evidence source object required: {evidence_id}")
    return {
        "schema_version": CANONICAL_EVIDENCE_SCHEMA_VERSION,
        "evidence_id": evidence_id,
        "source_role": role,
        "surfaces": surfaces,
        "normalized_surfaces": _stable_unique(normalize_key(value) for value in surfaces),
        "readings": readings,
        "part_of_speech": pos,
        "payload": payload,
        "source": _validate_source(source, evidence_id),
    }


def load_evidence_records(roots: Iterable[Path]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    ids: set[str] = set()
    for path in _iter_evidence_paths(roots):
        opener = gzip.open if path.name.endswith(".gz") else Path.open
        with opener(path, "rt", encoding="utf-8") as handle:  # type: ignore[arg-type]
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                raw = json.loads(line)
                if not isinstance(raw, dict):
                    raise ValueError(
                        f"canonical evidence row must be object: {path}:{line_number}"
                    )
                value = normalize_evidence_record(raw, path=path, line=line_number)
                if value["evidence_id"] in ids:
                    raise ValueError(
                        f"duplicate canonical evidence id: {value['evidence_id']}"
                    )
                ids.add(value["evidence_id"])
                values.append(value)
    values.sort(key=lambda row: row["evidence_id"])
    return values


def _candidate_dictionary_ids(
    evidence: dict[str, Any],
    records: dict[str, dict[str, Any]],
    surface_index: dict[str, set[str]],
) -> list[str]:
    candidates: set[str] = set()
    for surface in evidence["normalized_surfaces"]:
        candidates.update(surface_index.get(surface, set()))
    if not candidates:
        return []

    evidence_readings = set(evidence.get("readings") or [])
    evidence_pos = set(evidence.get("part_of_speech") or [])
    selected: list[str] = []
    for dictionary_id in sorted(candidates):
        record = records[dictionary_id]
        record_readings = {normalize_key(value) for value in record.get("readings") or []}
        record_pos = {normalize_key(value) for value in record.get("part_of_speech") or []}
        if evidence_readings and record_readings and not (evidence_readings & record_readings):
            continue
        if evidence_pos and record_pos and not (evidence_pos & record_pos):
            continue
        selected.append(dictionary_id)
    return selected


def attach_auxiliary_evidence(
    records: list[dict[str, Any]],
    evidence_records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_id = {record["dictionary_id"]: dict(record) for record in records}
    surface_index: dict[str, set[str]] = defaultdict(set)
    for record in by_id.values():
        for surface in record.get("normalized_surfaces") or []:
            surface_index[normalize_key(surface)].add(record["dictionary_id"])

    report: list[dict[str, Any]] = []
    for evidence in evidence_records:
        candidates = _candidate_dictionary_ids(evidence, by_id, surface_index)
        if len(candidates) == 1:
            dictionary_id = candidates[0]
            record = by_id[dictionary_id]
            facets = dict(record.get("auxiliary_evidence") or {})
            role_values = list(facets.get(evidence["source_role"]) or [])
            role_values.append(evidence)
            role_values.sort(key=lambda row: row["evidence_id"])
            facets[evidence["source_role"]] = role_values
            record["auxiliary_evidence"] = dict(sorted(facets.items()))
            record["auxiliary_evidence_count"] = sum(
                len(values) for values in record["auxiliary_evidence"].values()
            )
            by_id[dictionary_id] = record
            status = "attached"
        elif not candidates:
            dictionary_id = None
            status = "unmatched"
        else:
            dictionary_id = None
            status = "ambiguous"
        report.append(
            {
                "evidence_id": evidence["evidence_id"],
                "source_role": evidence["source_role"],
                "status": status,
                "dictionary_id": dictionary_id,
                "candidate_dictionary_ids": candidates,
                "automatic_meaning_generation": False,
            }
        )

    result = [by_id[key] for key in sorted(by_id)]
    report.sort(key=lambda row: row["evidence_id"])
    return result, report


def _write_gzip(path: Path, payload: bytes) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw,
            compresslevel=9,
            mtime=0,
        ) as handle:
            handle.write(payload)
    return {
        "path": str(path),
        "sha256": _sha256_file(path),
        "bytes": path.stat().st_size,
        "uncompressed_sha256": _sha256_bytes(payload),
        "uncompressed_bytes": len(payload),
    }


def compile_evidence_enriched_dictionary(
    canonical_root: Path,
    evidence_roots: Iterable[Path],
    output_root: Path,
    *,
    shard_size: int = 10000,
) -> dict[str, Any]:
    if shard_size < 100:
        raise ValueError("shard-size must be at least 100")
    master_manifest = validate_compiled_dictionary_root(canonical_root)
    base_records = list(_iter_dictionary_records(canonical_root))
    evidence_records = load_evidence_records(evidence_roots)
    records, join_report = attach_auxiliary_evidence(base_records, evidence_records)

    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    surface_index: dict[str, set[str]] = defaultdict(set)
    reading_index: dict[str, set[str]] = defaultdict(set)
    lemma_index: dict[str, set[str]] = defaultdict(set)
    pos_index: dict[str, set[str]] = defaultdict(set)
    domain_index: dict[str, set[str]] = defaultdict(set)
    sense_index: dict[str, str] = {}
    source_record_index: dict[str, str] = {}
    record_locator: dict[str, dict[str, int]] = {}
    role_counts: Counter[str] = Counter()

    for number, record in enumerate(records):
        dictionary_id = record["dictionary_id"]
        record_locator[dictionary_id] = {
            "shard": number // shard_size,
            "line": number % shard_size + 1,
        }
        lemma_index[normalize_key(record["lemma"])].add(dictionary_id)
        for value in record["normalized_surfaces"]:
            surface_index[normalize_key(value)].add(dictionary_id)
        for value in record["readings"]:
            reading_index[normalize_key(value)].add(dictionary_id)
        for value in record["part_of_speech"]:
            pos_index[normalize_key(value)].add(dictionary_id)
        for value in record.get("domains") or []:
            domain_index[normalize_key(value)].add(dictionary_id)
        for sense in record.get("senses") or []:
            sense_index[sense["sense_id"]] = dictionary_id
        for source in record.get("source_evidence") or []:
            source_record_index[source["source_record_id"]] = dictionary_id
        for role, values in (record.get("auxiliary_evidence") or {}).items():
            role_counts[role] += len(values)

    outputs: list[dict[str, Any]] = []
    indexes: dict[str, Any] = {
        "surface-index.json.gz": {key: sorted(values) for key, values in sorted(surface_index.items())},
        "reading-index.json.gz": {key: sorted(values) for key, values in sorted(reading_index.items())},
        "lemma-index.json.gz": {key: sorted(values) for key, values in sorted(lemma_index.items())},
        "pos-index.json.gz": {key: sorted(values) for key, values in sorted(pos_index.items())},
        "domain-index.json.gz": {key: sorted(values) for key, values in sorted(domain_index.items())},
        "sense-index.json.gz": dict(sorted(sense_index.items())),
        "source-record-index.json.gz": dict(sorted(source_record_index.items())),
        "record-locator.json.gz": dict(sorted(record_locator.items())),
    }
    for name, mapping in indexes.items():
        payload = (_json_line(mapping) + "\n").encode("utf-8")
        meta = _write_gzip(output_root / "indexes" / name, payload)
        meta["path"] = f"indexes/{name}"
        outputs.append(meta)

    for start in range(0, len(records), shard_size):
        selected = records[start : start + shard_size]
        payload = b"".join((_json_line(item) + "\n").encode("utf-8") for item in selected)
        relative = f"records/dictionary-{start // shard_size:04d}.jsonl.gz"
        meta = _write_gzip(output_root / relative, payload)
        meta["path"] = relative
        meta["record_count"] = len(selected)
        outputs.append(meta)

    join_text = "".join(_json_line(item) + "\n" for item in join_report)
    join_path = output_root / "auxiliary-evidence-join-report.jsonl"
    join_path.write_text(join_text, encoding="utf-8", newline="\n")
    outputs.append({
        "path": join_path.name,
        "sha256": _sha256_file(join_path),
        "bytes": join_path.stat().st_size,
        "record_count": len(join_report),
    })
    status_counts = Counter(item["status"] for item in join_report)
    manifest = {
        "schema_version": master_manifest["schema_version"],
        "evidence_schema_version": CANONICAL_EVIDENCE_SCHEMA_VERSION,
        "mode": "mcp-canonical-dictionary",
        "dictionary_view": "evidence-enriched",
        "record_count": len(records),
        "sense_count": sum(len(record.get("senses") or []) for record in records),
        "source_evidence_count": sum(len(record.get("source_evidence") or []) for record in records),
        "auxiliary_evidence_count": len(evidence_records),
        "auxiliary_evidence_role_counts": dict(sorted(role_counts.items())),
        "auxiliary_join_status_counts": dict(sorted(status_counts.items())),
        "record_shard_size": shard_size,
        "record_shards": ((len(records) + shard_size - 1) // shard_size if records else 0),
        "master_dictionary_manifest_sha256": _sha256_file(canonical_root / "manifest.json"),
        "boundaries": {
            "canonical_project_dictionary_schema": True,
            "upstream_sources_are_evidence_not_runtime_dependencies": True,
            "runtime_external_dictionary_lookup": False,
            "automatic_meaning_generation": False,
            "approved_meaning_only": True,
            "preserve_multiple_senses": True,
            "preserve_source_provenance_and_license": True,
            "auxiliary_evidence_never_becomes_definition_automatically": True,
            "ambiguous_auxiliary_join_is_not_attached": True,
        },
        "outputs": outputs,
    }
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    validate_compiled_dictionary_root(output_root)
    return manifest
