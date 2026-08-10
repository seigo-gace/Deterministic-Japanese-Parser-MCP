"""Build the public-compatible view of the MCP canonical dictionary.

The canonical master/evidence-enriched dictionary may preserve approved evidence from
sources whose redistribution terms differ. This stage removes source evidence that is
not eligible for the default public-distributable dictionary and drops senses/records
that would otherwise have no distributable meaning evidence. Auxiliary evidence is
filtered under the same rule. No meaning is generated or reinterpreted here.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import gzip
import json
from pathlib import Path
import shutil
from typing import Any, Iterable

from .canonical_dictionary import validate_compiled_dictionary_root
from .common import _json_line, _sha256_bytes, _sha256_file, normalize_key
from .license_policy import classify_data_license

PUBLIC_DICTIONARY_VIEW_VERSION = "1.1.0"


def _stable_unique(values: Iterable[Any]) -> list[str]:
    return sorted({str(value or "").strip() for value in values if str(value or "").strip()})


def _iter_master_records(root: Path) -> Iterable[dict[str, Any]]:
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


def _allowed_evidence(
    rows: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    allowed: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        classification = classify_data_license(item.get("license"))
        item["distribution_license"] = classification
        if classification["public_dictionary_allowed"] is True:
            allowed.append(item)
        else:
            excluded.append(item)
    allowed.sort(key=_json_line)
    excluded.sort(key=_json_line)
    return allowed, excluded


def _filter_auxiliary_evidence(
    record: dict[str, Any],
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    excluded_rows: list[dict[str, Any]] = []
    for role, rows in sorted((record.get("auxiliary_evidence") or {}).items()):
        allowed_role: list[dict[str, Any]] = []
        for evidence in rows or []:
            source = evidence.get("source") or {}
            classification = classify_data_license(source.get("license"))
            copied = dict(evidence)
            copied["distribution_license"] = classification
            if classification["public_dictionary_allowed"] is True:
                allowed_role.append(copied)
            else:
                excluded_rows.append(
                    {
                        "kind": "auxiliary-evidence",
                        "dictionary_id": record.get("dictionary_id"),
                        "sense_id": None,
                        "evidence_id": evidence.get("evidence_id"),
                        "source_role": role,
                        "source_record_id": source.get("source_id"),
                        "dataset": source.get("dataset"),
                        "license": source.get("license"),
                        "tier": classification["tier"],
                        "reason": classification["reason"],
                    }
                )
        if allowed_role:
            allowed_role.sort(key=lambda row: row["evidence_id"])
            result[role] = allowed_role
    return dict(sorted(result.items())), sorted(excluded_rows, key=_json_line)


def public_record_view(
    record: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    excluded_rows: list[dict[str, Any]] = []
    senses: list[dict[str, Any]] = []
    allowed_source_ids: set[str] = set()

    for sense in record.get("senses") or []:
        allowed, excluded = _allowed_evidence(sense.get("source_evidence") or [])
        for row in excluded:
            excluded_rows.append(
                {
                    "kind": "meaning-source-evidence",
                    "dictionary_id": record.get("dictionary_id"),
                    "sense_id": sense.get("sense_id"),
                    "evidence_id": None,
                    "source_role": "meaning",
                    "source_record_id": row.get("source_record_id"),
                    "dataset": row.get("dataset"),
                    "license": row.get("license"),
                    "tier": row["distribution_license"]["tier"],
                    "reason": row["distribution_license"]["reason"],
                }
            )
        if not allowed:
            continue
        copied = dict(sense)
        copied["source_evidence"] = allowed
        copied["evidence_count"] = len(allowed)
        senses.append(copied)
        allowed_source_ids.update(
            str(row.get("source_record_id"))
            for row in allowed
            if row.get("source_record_id")
        )

    if not senses:
        return None, sorted(excluded_rows, key=_json_line)

    record_evidence, record_excluded = _allowed_evidence(
        record.get("source_evidence") or []
    )
    for row in record_excluded:
        source_record_id = str(row.get("source_record_id") or "")
        if not any(
            item.get("source_record_id") == source_record_id
            and item.get("kind") == "meaning-source-evidence"
            for item in excluded_rows
        ):
            excluded_rows.append(
                {
                    "kind": "meaning-source-evidence",
                    "dictionary_id": record.get("dictionary_id"),
                    "sense_id": None,
                    "evidence_id": None,
                    "source_role": "meaning",
                    "source_record_id": source_record_id,
                    "dataset": row.get("dataset"),
                    "license": row.get("license"),
                    "tier": row["distribution_license"]["tier"],
                    "reason": row["distribution_license"]["reason"],
                }
            )
    record_evidence = [
        row
        for row in record_evidence
        if str(row.get("source_record_id") or "") in allowed_source_ids
    ]
    if not record_evidence:
        return None, sorted(excluded_rows, key=_json_line)

    auxiliary, auxiliary_excluded = _filter_auxiliary_evidence(record)
    excluded_rows.extend(auxiliary_excluded)
    tiers = _stable_unique(
        (row.get("distribution_license") or {}).get("tier")
        for row in record_evidence
    )
    auxiliary_tiers = _stable_unique(
        (item.get("distribution_license") or {}).get("tier")
        for values in auxiliary.values()
        for item in values
    )
    public = dict(record)
    public["senses"] = senses
    public["source_evidence"] = record_evidence
    public["source_record_ids"] = sorted(allowed_source_ids)
    public["source_evidence_count"] = len(record_evidence)
    public["auxiliary_evidence"] = auxiliary
    public["auxiliary_evidence_count"] = sum(len(values) for values in auxiliary.values())
    public["distribution"] = {
        "view": "public-compatible",
        "meaning_license_tiers": tiers,
        "auxiliary_license_tiers": auxiliary_tiers,
        "contains_noncommercial_source": False,
        "contains_no_derivatives_source": False,
        "excluded_source_evidence_count": len(excluded_rows),
    }
    public["boundaries"] = {
        **dict(public.get("boundaries") or {}),
        "public_distribution_view": True,
        "license_incompatible_evidence_excluded": True,
    }
    return public, sorted(excluded_rows, key=_json_line)


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


def compile_public_dictionary_view(
    canonical_root: Path,
    output_root: Path,
    *,
    shard_size: int = 10000,
) -> dict[str, Any]:
    if shard_size < 100:
        raise ValueError("shard-size must be at least 100")
    master_manifest = validate_compiled_dictionary_root(canonical_root)
    records: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    for master_record in _iter_master_records(canonical_root):
        public, excluded = public_record_view(master_record)
        exclusions.extend(excluded)
        if public is not None:
            records.append(public)
    records.sort(key=lambda row: row["dictionary_id"])
    exclusions.sort(key=_json_line)

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
    tier_counts: Counter[str] = Counter()
    auxiliary_tier_counts: Counter[str] = Counter()
    dataset_counts: Counter[str] = Counter()
    auxiliary_role_counts: Counter[str] = Counter()
    source_evidence_count = 0
    auxiliary_evidence_count = 0
    sense_count = 0

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
        for sense in record["senses"]:
            sense_index[sense["sense_id"]] = dictionary_id
            sense_count += 1
        for source in record["source_evidence"]:
            source_record_index[source["source_record_id"]] = dictionary_id
            classification = source.get("distribution_license") or {}
            tier_counts[str(classification.get("tier") or "unknown")] += 1
            dataset_counts[str(source.get("dataset") or "")] += 1
            source_evidence_count += 1
        for role, values in (record.get("auxiliary_evidence") or {}).items():
            auxiliary_role_counts[role] += len(values)
            auxiliary_evidence_count += len(values)
            for item in values:
                classification = item.get("distribution_license") or {}
                auxiliary_tier_counts[str(classification.get("tier") or "unknown")] += 1

    outputs: list[dict[str, Any]] = []
    indexes: dict[str, Any] = {
        "surface-index.json.gz": {
            key: sorted(values) for key, values in sorted(surface_index.items())
        },
        "reading-index.json.gz": {
            key: sorted(values) for key, values in sorted(reading_index.items())
        },
        "lemma-index.json.gz": {
            key: sorted(values) for key, values in sorted(lemma_index.items())
        },
        "pos-index.json.gz": {
            key: sorted(values) for key, values in sorted(pos_index.items())
        },
        "domain-index.json.gz": {
            key: sorted(values) for key, values in sorted(domain_index.items())
        },
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
            (_json_line(item) + "\n").encode("utf-8")
            for item in selected
        )
        relative = f"records/dictionary-{start // shard_size:04d}.jsonl.gz"
        meta = _write_gzip(output_root / relative, payload)
        meta["path"] = relative
        meta["record_count"] = len(selected)
        outputs.append(meta)

    exclusion_text = "".join(_json_line(item) + "\n" for item in exclusions)
    exclusion_path = output_root / "license-exclusions.jsonl"
    exclusion_path.write_text(exclusion_text, encoding="utf-8", newline="\n")
    outputs.append(
        {
            "path": "license-exclusions.jsonl",
            "sha256": _sha256_file(exclusion_path),
            "bytes": exclusion_path.stat().st_size,
            "record_count": len(exclusions),
        }
    )

    manifest = {
        "schema_version": master_manifest["schema_version"],
        "view_version": PUBLIC_DICTIONARY_VIEW_VERSION,
        "mode": "mcp-canonical-dictionary",
        "distribution_view": "public-compatible",
        "record_count": len(records),
        "sense_count": sense_count,
        "source_evidence_count": source_evidence_count,
        "auxiliary_evidence_count": auxiliary_evidence_count,
        "license_exclusion_count": len(exclusions),
        "license_tier_counts": dict(sorted(tier_counts.items())),
        "auxiliary_license_tier_counts": dict(sorted(auxiliary_tier_counts.items())),
        "auxiliary_role_counts": dict(sorted(auxiliary_role_counts.items())),
        "dataset_counts": dict(sorted(dataset_counts.items())),
        "record_shard_size": shard_size,
        "record_shards": (
            (len(records) + shard_size - 1) // shard_size if records else 0
        ),
        "master_dictionary_manifest_sha256": _sha256_file(
            canonical_root / "manifest.json"
        ),
        "boundaries": {
            "canonical_project_dictionary_schema": True,
            "upstream_sources_are_evidence_not_runtime_dependencies": True,
            "runtime_external_dictionary_lookup": False,
            "automatic_meaning_generation": False,
            "approved_meaning_only": True,
            "preserve_multiple_senses": True,
            "preserve_source_provenance_and_license": True,
            "public_distribution_view": True,
            "noncommercial_source_auto_promotion": False,
            "no_derivatives_source_auto_promotion": False,
            "auxiliary_evidence_license_filtered": True,
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
