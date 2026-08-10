"""Compile approved factory records into the MCP-owned canonical dictionary schema.

This is a build-time projection. External dictionaries remain evidence sources; they are
not queried at runtime and they are not treated as the MCP's canonical dictionary.
Only explicit, approved semantic meanings are allowed into this compiled dictionary.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any, Iterable

from .common import _as_list, _iter_jsonl, _json_line, _sha256_bytes, _sha256_file, normalize_key
from .semantic_labeler import candidate_has_real_meaning

CANONICAL_DICTIONARY_SCHEMA_VERSION = "1.0.0"


def _stable_unique(values: Iterable[Any]) -> list[str]:
    return sorted({str(value or "").strip() for value in values if str(value or "").strip()})


def _stable_objects(values: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    by_signature: dict[str, dict[str, Any]] = {}
    for value in values:
        signature = _json_line(value)
        by_signature[signature] = value
    return [by_signature[key] for key in sorted(by_signature)]


def _approved_scopes(record: dict[str, Any]) -> set[str]:
    return set((record.get("approval") or {}).get("approved_scopes") or [])


def _canonical_identity(record: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    lemma = str(record.get("lemma") or "").strip()
    readings = _stable_unique(normalize_key(v) for v in _as_list(record.get("readings")))
    parts = _stable_unique(normalize_key(v) for v in _as_list(record.get("part_of_speech")))
    if not lemma or not readings or not parts:
        raise ValueError(
            f"canonical dictionary identity requires lemma/readings/part_of_speech: "
            f"{record.get('record_id')}"
        )
    signature = {
        "lemma": normalize_key(lemma),
        "readings": readings,
        "part_of_speech": parts,
    }
    digest = _sha256_bytes(_json_line(signature).encode("utf-8"))[:24]
    return f"CDICT-{digest}", signature


def _source_evidence(record: dict[str, Any]) -> dict[str, Any]:
    source = record.get("source") or {}
    return {
        "source_record_id": str(record.get("record_id") or ""),
        "dataset": str(source.get("dataset") or ""),
        "version": str(source.get("version") or ""),
        "license": str(source.get("license") or ""),
        "source_id": str(source.get("source_id") or ""),
        "source_url": str(source.get("source_url") or ""),
        "source_sha256": str(source.get("source_sha256") or ""),
        "attribution": str(source.get("attribution") or ""),
        "input_sha256": str(record.get("input_sha256") or ""),
    }


def _candidate_glosses(candidate: dict[str, Any]) -> list[str]:
    return _stable_unique(
        [
            *_as_list(candidate.get("glosses")),
            *_as_list(candidate.get("definitions")),
            candidate.get("gloss"),
            candidate.get("meaning"),
        ]
    )


def _sense_signature(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "glosses": _candidate_glosses(candidate),
        "part_of_speech": _stable_unique(candidate.get("part_of_speech") or []),
        "domains": _stable_unique(candidate.get("domains") or []),
        "parameters": candidate.get("parameters") or {},
        "register": candidate.get("register") or {},
        "context": candidate.get("context") or {},
    }


def _merge_senses(
    dictionary_id: str,
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for record in records:
        evidence = _source_evidence(record)
        for candidate in _as_list(record.get("meaning_candidates")):
            if not isinstance(candidate, dict):
                continue
            if candidate.get("review_status", "approved") != "approved":
                continue
            if not candidate_has_real_meaning(candidate):
                continue
            signature_value = _sense_signature(candidate)
            signature = _json_line(signature_value)
            item = grouped.setdefault(
                signature,
                {
                    "signature": signature_value,
                    "labels": set(),
                    "evidence": [],
                },
            )
            label = str(candidate.get("label") or "").strip()
            if label:
                item["labels"].add(label)
            item["evidence"].append(evidence)

    senses: list[dict[str, Any]] = []
    for signature, item in sorted(grouped.items()):
        material = signature.encode("utf-8")
        sense_id = f"{dictionary_id}:S-{hashlib.sha256(material).hexdigest()[:16]}"
        evidence_rows = _stable_objects(item["evidence"])
        senses.append(
            {
                "sense_id": sense_id,
                "labels": sorted(item["labels"]),
                "glosses": item["signature"]["glosses"],
                "part_of_speech": item["signature"]["part_of_speech"],
                "domains": item["signature"]["domains"],
                "parameters": item["signature"]["parameters"],
                "register": item["signature"]["register"],
                "context": item["signature"]["context"],
                "evidence_count": len(evidence_rows),
                "source_evidence": evidence_rows,
            }
        )
    return senses


def _merge_morphology(records: list[dict[str, Any]]) -> dict[str, Any]:
    forms: list[dict[str, Any]] = []
    conjugations: list[dict[str, Any]] = []
    backends: set[str] = set()
    for record in records:
        morphology = record.get("morphology") or {}
        backend = str(morphology.get("backend") or "").strip()
        if backend:
            backends.add(backend)
        for form in _as_list(morphology.get("forms")):
            if isinstance(form, dict):
                forms.append(form)
        conjugation = morphology.get("conjugation")
        if isinstance(conjugation, dict) and conjugation:
            conjugations.append(
                {
                    "source_record_id": record.get("record_id"),
                    "value": conjugation,
                }
            )
    return {
        "backends": sorted(backends),
        "forms": _stable_objects(forms),
        "conjugation_evidence": _stable_objects(conjugations),
    }


def _merge_pragmatics(records: list[dict[str, Any]]) -> dict[str, Any]:
    examples: dict[str, list[dict[str, Any]]] = {
        "positive": [],
        "negative": [],
        "boundary": [],
    }
    contexts: list[dict[str, Any]] = []
    registers: list[dict[str, Any]] = []
    for record in records:
        if "pragmatic" not in _approved_scopes(record):
            continue
        record_examples = record.get("examples") or {}
        for kind in examples:
            for value in _as_list(record_examples.get(kind)):
                text = str(value or "").strip()
                if text:
                    examples[kind].append(
                        {
                            "text": text,
                            "source_record_id": record.get("record_id"),
                        }
                    )
        context = record.get("context_conditions") or {}
        if context:
            contexts.append(
                {
                    "source_record_id": record.get("record_id"),
                    "value": context,
                }
            )
        register = record.get("register") or {}
        if register:
            registers.append(
                {
                    "source_record_id": record.get("record_id"),
                    "value": register,
                }
            )
    return {
        "examples": {
            kind: _stable_objects(values)
            for kind, values in sorted(examples.items())
        },
        "context_evidence": _stable_objects(contexts),
        "register_evidence": _stable_objects(registers),
    }


def _merge_semantic_facets(records: list[dict[str, Any]]) -> dict[str, Any]:
    polarity: list[dict[str, Any]] = []
    feature_types: set[str] = set()
    semantic_targets: set[str] = set()
    usage_labels: set[str] = set()
    risk_classes: set[str] = set()
    for record in records:
        feature = str(record.get("feature_type") or "").strip()
        if feature:
            feature_types.add(feature)
        semantic_targets.update(_stable_unique(_as_list(record.get("semantic_targets"))))
        usage_labels.update(_stable_unique(_as_list(record.get("usage_labels"))))
        risk_class = str(record.get("risk_class") or "").strip()
        if risk_class:
            risk_classes.add(risk_class)
        if "semantic" in _approved_scopes(record):
            p = str(record.get("polarity") or "unspecified")
            intensity = record.get("intensity")
            if p != "unspecified" or intensity is not None:
                polarity.append(
                    {
                        "source_record_id": record.get("record_id"),
                        "polarity": p,
                        "intensity": intensity,
                    }
                )
    return {
        "feature_types": sorted(feature_types),
        "semantic_targets": sorted(semantic_targets),
        "usage_labels": sorted(usage_labels),
        "risk_classes": sorted(risk_classes),
        "sentiment_evidence": _stable_objects(polarity),
    }


def _build_dictionary_record(
    dictionary_id: str,
    identity: dict[str, Any],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    senses = _merge_senses(dictionary_id, records)
    if not senses:
        raise ValueError(f"canonical dictionary record has no approved real meaning: {dictionary_id}")

    surfaces = _stable_unique(
        value
        for record in records
        for value in _as_list(record.get("surfaces"))
    )
    normalized_surfaces = _stable_unique(
        value
        for record in records
        for value in _as_list(record.get("normalized_surfaces"))
    )
    readings = _stable_unique(
        value
        for record in records
        for value in _as_list(record.get("readings"))
    )
    parts = _stable_unique(
        value
        for record in records
        for value in _as_list(record.get("part_of_speech"))
    )
    domains = _stable_unique(
        value
        for record in records
        for value in _as_list(record.get("domains"))
    )
    source_evidence = _stable_objects(_source_evidence(record) for record in records)
    source_record_ids = sorted(str(record.get("record_id")) for record in records)

    return {
        "schema_version": CANONICAL_DICTIONARY_SCHEMA_VERSION,
        "dictionary_id": dictionary_id,
        "identity": identity,
        "lemma": str(records[0].get("lemma") or "").strip(),
        "surfaces": surfaces,
        "normalized_surfaces": normalized_surfaces,
        "readings": readings,
        "part_of_speech": parts,
        "morphology": _merge_morphology(records),
        "domains": domains,
        "senses": senses,
        "pragmatics": _merge_pragmatics(records),
        "semantic_facets": _merge_semantic_facets(records),
        "source_record_ids": source_record_ids,
        "source_evidence": source_evidence,
        "source_evidence_count": len(source_evidence),
        "boundaries": {
            "canonical_project_dictionary_record": True,
            "runtime_external_dictionary_lookup": False,
            "automatic_meaning_generation": False,
            "approved_meaning_only": True,
            "preserve_multiple_senses": True,
            "preserve_source_provenance": True,
        },
    }


def build_canonical_dictionary_records(review_root: Path) -> list[dict[str, Any]]:
    source_path = review_root / "approved-records.jsonl"
    if not source_path.is_file():
        raise FileNotFoundError(source_path)

    groups: dict[str, dict[str, Any]] = {}
    for record in _iter_jsonl(source_path):
        scopes = _approved_scopes(record)
        if "lexical" not in scopes or "semantic" not in scopes:
            continue
        if record.get("runtime_eligible") is not True:
            continue
        candidates = [
            candidate
            for candidate in _as_list(record.get("meaning_candidates"))
            if isinstance(candidate, dict)
            and candidate.get("review_status", "approved") == "approved"
            and candidate_has_real_meaning(candidate)
        ]
        if not candidates:
            continue
        dictionary_id, identity = _canonical_identity(record)
        group = groups.setdefault(
            dictionary_id,
            {
                "identity": identity,
                "records": [],
            },
        )
        if group["identity"] != identity:
            raise RuntimeError(f"canonical dictionary hash collision: {dictionary_id}")
        group["records"].append(record)

    result = [
        _build_dictionary_record(
            dictionary_id,
            group["identity"],
            sorted(group["records"], key=lambda row: str(row.get("record_id"))),
        )
        for dictionary_id, group in sorted(groups.items())
    ]
    validate_canonical_dictionary(result)
    return result


def validate_canonical_dictionary(records: list[dict[str, Any]]) -> None:
    ids: set[str] = set()
    sense_ids: set[str] = set()
    for record in records:
        dictionary_id = str(record.get("dictionary_id") or "")
        if not dictionary_id or dictionary_id in ids:
            raise ValueError(f"duplicate or empty canonical dictionary id: {dictionary_id}")
        ids.add(dictionary_id)
        for required in ("lemma", "surfaces", "readings", "part_of_speech", "senses", "source_evidence"):
            if not record.get(required):
                raise ValueError(f"canonical dictionary field required: {dictionary_id}:{required}")
        for sense in record["senses"]:
            sense_id = str(sense.get("sense_id") or "")
            if not sense_id or sense_id in sense_ids:
                raise ValueError(f"duplicate or empty sense id: {sense_id}")
            sense_ids.add(sense_id)
            if not sense.get("glosses"):
                raise ValueError(f"meaning gloss required: {sense_id}")
            if not sense.get("source_evidence"):
                raise ValueError(f"meaning evidence required: {sense_id}")


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


def compile_canonical_dictionary(
    review_root: Path,
    output_root: Path,
    *,
    shard_size: int = 10000,
) -> dict[str, Any]:
    if shard_size < 100:
        raise ValueError("shard-size must be at least 100")

    records = build_canonical_dictionary_records(review_root)
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
    dataset_counts: Counter[str] = Counter()
    source_evidence_count = 0
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
        for value in record["domains"]:
            domain_index[normalize_key(value)].add(dictionary_id)
        for sense in record["senses"]:
            sense_index[sense["sense_id"]] = dictionary_id
            sense_count += 1
        for source in record["source_evidence"]:
            source_record_index[source["source_record_id"]] = dictionary_id
            dataset_counts[source["dataset"]] += 1
            source_evidence_count += 1

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

    manifest = {
        "schema_version": CANONICAL_DICTIONARY_SCHEMA_VERSION,
        "mode": "mcp-canonical-dictionary",
        "record_count": len(records),
        "sense_count": sense_count,
        "source_evidence_count": source_evidence_count,
        "dataset_counts": dict(sorted(dataset_counts.items())),
        "record_shard_size": shard_size,
        "record_shards": (
            (len(records) + shard_size - 1) // shard_size if records else 0
        ),
        "source_review_manifest_sha256": _sha256_file(review_root / "manifest.json"),
        "boundaries": {
            "canonical_project_dictionary_schema": True,
            "upstream_sources_are_evidence_not_runtime_dependencies": True,
            "runtime_external_dictionary_lookup": False,
            "automatic_meaning_generation": False,
            "approved_meaning_only": True,
            "preserve_multiple_senses": True,
            "preserve_source_provenance_and_license": True,
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


def validate_compiled_dictionary_root(root: Path) -> dict[str, Any]:
    """Validate the compiled dictionary as a standalone searchable artifact."""
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("mode") != "mcp-canonical-dictionary":
        raise ValueError("canonical dictionary manifest mode mismatch")
    boundaries = manifest.get("boundaries") or {}
    required_boundaries = {
        "canonical_project_dictionary_schema": True,
        "upstream_sources_are_evidence_not_runtime_dependencies": True,
        "runtime_external_dictionary_lookup": False,
        "automatic_meaning_generation": False,
        "approved_meaning_only": True,
        "preserve_multiple_senses": True,
        "preserve_source_provenance_and_license": True,
    }
    for key, expected in required_boundaries.items():
        if boundaries.get(key) is not expected:
            raise ValueError(f"canonical dictionary boundary mismatch: {key}")
    for output in manifest.get("outputs") or []:
        path = root / str(output.get("path") or "")
        if not path.is_file():
            raise FileNotFoundError(path)
        expected_sha = str(output.get("sha256") or "")
        if expected_sha and _sha256_file(path) != expected_sha:
            raise ValueError(f"canonical dictionary output digest mismatch: {path}")
    required_indexes = {
        "surface-index.json.gz",
        "reading-index.json.gz",
        "lemma-index.json.gz",
        "pos-index.json.gz",
        "domain-index.json.gz",
        "sense-index.json.gz",
        "source-record-index.json.gz",
        "record-locator.json.gz",
    }
    missing = [
        name for name in sorted(required_indexes)
        if not (root / "indexes" / name).is_file()
    ]
    if missing:
        raise FileNotFoundError(
            "canonical dictionary indexes incomplete: " + ", ".join(missing)
        )
    with gzip.open(
        root / "indexes/record-locator.json.gz", "rt", encoding="utf-8"
    ) as handle:
        locator = json.load(handle)
    if len(locator) != int(manifest.get("record_count", 0)):
        raise ValueError("canonical dictionary locator count mismatch")
    return manifest
