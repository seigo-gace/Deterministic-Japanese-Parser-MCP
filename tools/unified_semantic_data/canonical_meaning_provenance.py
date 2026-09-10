"""Refine canonical sense provenance using the semantic-enrichment review queue.

When a record without a definition receives a reviewed candidate from an approved record
or local semantic reference pack, the canonical sense must point to the source that
actually supplied that definition. This stage replaces fallback target-record evidence
with recorded reference evidence when the approved sense gloss exactly matches the
proposal. It never changes the meaning text itself.
"""
from __future__ import annotations

from collections import defaultdict
import gzip
import json
from pathlib import Path
import shutil
from typing import Any, Iterable, Iterator

from .canonical_dictionary import validate_compiled_dictionary_root
from .common import _json_line, _sha256_bytes, _sha256_file, normalize_key

MEANING_PROVENANCE_VERSION = "1.1.0"


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


def _stable_objects(values: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    by_signature = {_json_line(value): value for value in values}
    return [by_signature[key] for key in sorted(by_signature)]


def _candidate_glosses(candidate: dict[str, Any]) -> tuple[str, ...]:
    values = [
        *_as_list(candidate.get("glosses")),
        *_as_list(candidate.get("definitions")),
        candidate.get("gloss"),
        candidate.get("meaning"),
    ]
    return tuple(_stable_unique(values))


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


def _reference_file_row(
    path_value: Any,
    source_id: str,
    cache: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    path_text = str(path_value or "").strip()
    key = (path_text, source_id)
    if key in cache:
        return cache[key]
    if not path_text or not source_id:
        cache[key] = {}
        return {}
    path = Path(path_text)
    if not path.is_file() or path.suffix != ".jsonl":
        cache[key] = {}
        return {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                continue
            row_source_id = str(
                value.get("source_id") or value.get("id") or value.get("record_id") or ""
            )
            if row_source_id == source_id:
                cache[key] = value
                return value
    cache[key] = {}
    return {}


def _reference_source_evidence(
    evidence: dict[str, Any],
    *,
    target_record_id: str,
    reference_cache: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    source = dict(evidence.get("source") or {})
    reference_record_id = str(evidence.get("reference_record_id") or "")
    source_record_id = str(
        source.get("source_id") or reference_record_id or "reference-unknown"
    )
    details = _reference_file_row(
        source.get("path"), source_record_id, reference_cache
    )
    detail_source = details.get("source") if isinstance(details.get("source"), dict) else {}

    def select(name: str, default: str = "") -> str:
        return str(
            source.get(name)
            or details.get(name)
            or detail_source.get(name)
            or default
        ).strip()

    return {
        "source_record_id": reference_record_id or source_record_id,
        "dataset": select("dataset", "semantic-reference"),
        "version": select("version"),
        "license": select("license"),
        "source_id": source_record_id,
        "source_url": select("source_url"),
        "source_sha256": select("source_sha256").lower(),
        "attribution": select("attribution"),
        "reference_path": str(source.get("path") or ""),
        "reference_score": evidence.get("score"),
        "derivation_target_record_id": target_record_id,
        "meaning_evidence_type": "semantic-enrichment-reference",
    }


def load_semantic_provenance(
    review_root: Path,
) -> dict[tuple[str, tuple[str, ...]], list[dict[str, Any]]]:
    queue_path = review_root / "semantic-enrichment-queue.jsonl"
    if not queue_path.is_file():
        return {}
    result: dict[tuple[str, tuple[str, ...]], list[dict[str, Any]]] = defaultdict(list)
    reference_cache: dict[tuple[str, str], dict[str, Any]] = {}
    with queue_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(
                    f"semantic enrichment queue row must be object: {queue_path}:{line_number}"
                )
            target_record_id = str(row.get("record_id") or "")
            evidence_by_id = {
                str(item.get("reference_record_id")): item
                for item in row.get("evidence") or []
                if isinstance(item, dict) and item.get("reference_record_id")
            }
            for candidate in row.get("proposed_meaning_candidates") or []:
                if not isinstance(candidate, dict):
                    continue
                signature = _candidate_glosses(candidate)
                if not target_record_id or not signature:
                    continue
                evidence_ids = _stable_unique(candidate.get("evidence_ids") or [])
                selected = [
                    evidence_by_id[value]
                    for value in evidence_ids
                    if value in evidence_by_id
                ]
                if not selected:
                    # Older queue rows did not bind evidence per candidate. Use all
                    # selected-reference evidence, but still only on exact gloss match.
                    selected = list(evidence_by_id.values())
                for evidence in selected:
                    result[(target_record_id, signature)].append(
                        _reference_source_evidence(
                            evidence,
                            target_record_id=target_record_id,
                            reference_cache=reference_cache,
                        )
                    )
    return {
        key: _stable_objects(values)
        for key, values in sorted(result.items(), key=lambda item: (item[0][0], item[0][1]))
    }


def refine_record_meaning_provenance(
    record: dict[str, Any],
    provenance: dict[tuple[str, tuple[str, ...]], list[dict[str, Any]]],
) -> tuple[dict[str, Any], int]:
    refined = dict(record)
    senses: list[dict[str, Any]] = []
    replacement_count = 0
    for sense in record.get("senses") or []:
        copied = dict(sense)
        signature = tuple(_stable_unique(sense.get("glosses") or []))
        new_evidence: list[dict[str, Any]] = []
        derived_for: set[str] = set()
        for source in sense.get("source_evidence") or []:
            target_record_id = str(source.get("source_record_id") or "")
            replacement = provenance.get((target_record_id, signature))
            if replacement:
                new_evidence.extend(replacement)
                derived_for.add(target_record_id)
                replacement_count += 1
            else:
                item = dict(source)
                item.setdefault("meaning_evidence_type", "source-authored-record")
                new_evidence.append(item)
        copied["source_evidence"] = _stable_objects(new_evidence)
        copied["evidence_count"] = len(copied["source_evidence"])
        copied["derivation_target_record_ids"] = sorted(derived_for)
        copied["meaning_provenance_mode"] = (
            "semantic-enrichment-reference"
            if derived_for
            else "source-authored-record"
        )
        senses.append(copied)
    refined["senses"] = senses
    refined["meaning_provenance_refinement_count"] = replacement_count
    refined["boundaries"] = {
        **dict(refined.get("boundaries") or {}),
        "sense_level_meaning_provenance": True,
        "meaning_text_unchanged_by_provenance_stage": True,
    }
    return refined, replacement_count


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


def compile_meaning_provenance_view(
    review_root: Path,
    canonical_root: Path,
    output_root: Path,
    *,
    shard_size: int = 10000,
) -> dict[str, Any]:
    if shard_size < 100:
        raise ValueError("shard-size must be at least 100")
    master_manifest = validate_compiled_dictionary_root(canonical_root)
    provenance = load_semantic_provenance(review_root)
    records: list[dict[str, Any]] = []
    total_replacements = 0
    for record in _iter_dictionary_records(canonical_root):
        refined, count = refine_record_meaning_provenance(record, provenance)
        records.append(refined)
        total_replacements += count
    records.sort(key=lambda row: row["dictionary_id"])

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
        payload = b"".join(
            (_json_line(item) + "\n").encode("utf-8") for item in selected
        )
        relative = f"records/dictionary-{start // shard_size:04d}.jsonl.gz"
        meta = _write_gzip(output_root / relative, payload)
        meta["path"] = relative
        meta["record_count"] = len(selected)
        outputs.append(meta)

    manifest = {
        "schema_version": master_manifest["schema_version"],
        "meaning_provenance_version": MEANING_PROVENANCE_VERSION,
        "mode": "mcp-canonical-dictionary",
        "dictionary_view": "meaning-provenance-refined",
        "record_count": len(records),
        "sense_count": sum(len(record.get("senses") or []) for record in records),
        "source_evidence_count": sum(len(record.get("source_evidence") or []) for record in records),
        "provenance_candidate_keys": len(provenance),
        "sense_source_replacement_count": total_replacements,
        "record_shard_size": shard_size,
        "record_shards": (
            (len(records) + shard_size - 1) // shard_size if records else 0
        ),
        "master_dictionary_manifest_sha256": _sha256_file(
            canonical_root / "manifest.json"
        ),
        "semantic_enrichment_queue_sha256": (
            _sha256_file(review_root / "semantic-enrichment-queue.jsonl")
            if (review_root / "semantic-enrichment-queue.jsonl").is_file()
            else None
        ),
        "boundaries": {
            "canonical_project_dictionary_schema": True,
            "upstream_sources_are_evidence_not_runtime_dependencies": True,
            "runtime_external_dictionary_lookup": False,
            "automatic_meaning_generation": False,
            "approved_meaning_only": True,
            "preserve_multiple_senses": True,
            "preserve_source_provenance_and_license": True,
            "sense_level_meaning_provenance": True,
            "meaning_text_unchanged_by_provenance_stage": True,
            "reference_pack_metadata_recovered_when_available": True,
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
