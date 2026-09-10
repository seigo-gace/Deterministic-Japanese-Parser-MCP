"""Project the MCP canonical dictionary into the current SemanticDataRuntime ABI.

The projection is build-time only. It does not resolve or generate meanings; every
runtime candidate comes from an already-approved canonical dictionary sense.
"""
from __future__ import annotations

from collections import defaultdict
import gzip
import json
from pathlib import Path
import shutil
from typing import Any, Iterable

from .canonical_dictionary import (
    CANONICAL_DICTIONARY_SCHEMA_VERSION,
    validate_compiled_dictionary_root,
)
from .common import _json_line, _sha256_bytes, _sha256_file, normalize_key


RUNTIME_PROJECTION_VERSION = "1.1.0"

_CONTEXT_CONDITION_KEYS = (
    "required_any",
    "required_all",
    "forbidden_any",
    "required_social",
    "required_discourse",
)


def _stable_unique(values: Iterable[Any]) -> list[str]:
    return sorted({str(value or "").strip() for value in values if str(value or "").strip()})


def _iter_canonical_records(root: Path) -> Iterable[dict[str, Any]]:
    manifest = validate_compiled_dictionary_root(root)
    shard_count = int(manifest.get("record_shards", 0))
    for shard in range(shard_count):
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


def _risk_class(record: dict[str, Any]) -> str:
    values = set(
        _stable_unique((record.get("semantic_facets") or {}).get("risk_classes") or [])
    )
    if "action" in values:
        return "action"
    if "social" in values:
        return "social"
    return "semantic"


def _feature_type(record: dict[str, Any]) -> str:
    values = _stable_unique(
        (record.get("semantic_facets") or {}).get("feature_types") or []
    )
    if len(values) == 1:
        return values[0]
    if values:
        return "canonical_dictionary"
    return ""


def _reading_mappings(record: dict[str, Any]) -> list[dict[str, Any]]:
    mappings: list[dict[str, Any]] = []
    mapped_readings: set[str] = set()
    all_readings = set(_stable_unique(record.get("readings") or []))
    for raw in record.get("reading_mappings") or []:
        if not isinstance(raw, dict):
            continue
        reading = str(raw.get("reading") or "").strip()
        if not reading:
            continue
        mapped_readings.add(reading)
        all_readings.add(reading)
        mappings.append(
            {
                "reading": reading,
                "restricted_to": _stable_unique(raw.get("restricted_to") or []),
                "no_kanji": bool(raw.get("no_kanji", False)),
            }
        )
    for reading in sorted(all_readings - mapped_readings):
        mappings.append(
            {
                "reading": reading,
                "restricted_to": [],
                "no_kanji": False,
            }
        )
    return sorted(
        mappings,
        key=lambda item: (
            item["reading"],
            item["restricted_to"],
            item["no_kanji"],
        ),
    )


def _common_context_conditions(record: dict[str, Any]) -> dict[str, list[str]]:
    """Project only conditions shared by every approved pragmatic source.

    Sense-specific conditions are already carried by each canonical sense. A
    union here would incorrectly require bridge, chopstick, and edge contexts at
    once, so the record-wide projection is deliberately the stable intersection.
    """
    evidence = (record.get("pragmatics") or {}).get("context_evidence") or []
    values = [
        item.get("value") or {}
        for item in evidence
        if isinstance(item, dict) and isinstance(item.get("value") or {}, dict)
    ]
    output: dict[str, list[str]] = {}
    for key in _CONTEXT_CONDITION_KEYS:
        if not values:
            output[key] = []
            continue
        common = set(_stable_unique(values[0].get(key) or []))
        for value in values[1:]:
            common.intersection_update(_stable_unique(value.get(key) or []))
        output[key] = sorted(common)
    return output


def _candidate(sense: dict[str, Any]) -> dict[str, Any]:
    glosses = _stable_unique(sense.get("glosses") or [])
    labels = _stable_unique(sense.get("labels") or [])
    if not glosses:
        raise ValueError(f"canonical runtime sense missing gloss: {sense.get('sense_id')}")
    evidence_ids = _stable_unique(
        f"canonical-source:{item.get('source_record_id')}"
        for item in sense.get("source_evidence") or []
        if item.get("source_record_id")
    )
    if not evidence_ids:
        raise ValueError(
            f"canonical runtime sense missing source evidence: {sense.get('sense_id')}"
        )
    return {
        "candidate_id": sense["sense_id"],
        "label": labels[0] if labels else glosses[0],
        "glosses": glosses,
        "part_of_speech": _stable_unique(sense.get("part_of_speech") or []),
        "domains": _stable_unique(sense.get("domains") or []),
        "polarity": "unspecified",
        "intensity": None,
        "parameters": sense.get("parameters") or {},
        "register": sense.get("register") or {},
        "context": sense.get("context") or {},
        "evidence_ids": evidence_ids,
        "review_status": "approved",
    }


def project_record(record: dict[str, Any]) -> dict[str, Any]:
    candidates = [_candidate(item) for item in record.get("senses") or []]
    if not candidates:
        raise ValueError(
            f"canonical runtime projection requires senses: {record.get('dictionary_id')}"
        )
    dictionary_id = str(record.get("dictionary_id") or "")
    if not dictionary_id:
        raise ValueError("canonical runtime projection requires dictionary_id")
    semantic_facets = record.get("semantic_facets") or {}
    semantic_targets = _stable_unique(semantic_facets.get("semantic_targets") or [])
    if not semantic_targets:
        semantic_targets = ["lexicon"]
    return {
        "schema_version": "2.0.0",
        "record_id": dictionary_id,
        "source_kind": "canonical_dictionary",
        "pack_namespace": "core",
        "lemma": record["lemma"],
        "surfaces": record["surfaces"],
        "normalized_surfaces": record["normalized_surfaces"],
        "readings": record["readings"],
        "reading_mappings": _reading_mappings(record),
        "part_of_speech": record["part_of_speech"],
        "morphology": record.get("morphology") or {},
        "domains": record.get("domains") or [],
        "usage_labels": semantic_facets.get("usage_labels") or [],
        "feature_type": _feature_type(record),
        "meaning_candidates": candidates,
        "polarity": "unspecified",
        "intensity": None,
        "semantic_targets": semantic_targets,
        "parameters": {},
        "register": {},
        "context_conditions": _common_context_conditions(record),
        "task_candidates": [],
        "examples": (record.get("pragmatics") or {}).get("examples") or {
            "positive": [],
            "negative": [],
            "boundary": [],
        },
        "risk_class": _risk_class(record),
        "external_action_risk": False,
        "source": {
            "dataset": "MCP Canonical Dictionary",
            "version": CANONICAL_DICTIONARY_SCHEMA_VERSION,
            "license": "derived; see canonical source_evidence",
            "source_id": dictionary_id,
            "source_url": "",
            "source_sha256": "",
            "evidence_scope": "runtime_compiled_projection",
            "attribution": "preserved in canonical source_evidence",
        },
        "approval": {
            "scopes": {
                "lexical": "approved",
                "semantic": "approved",
                "pragmatic": "approved",
                "task": "not-applicable",
                "external_action": "not-applicable",
            },
            "approved_scopes": ["lexical", "pragmatic", "semantic"],
            "review_scopes": [],
            "blockers_by_scope": {
                "lexical": [],
                "semantic": [],
                "pragmatic": [],
                "task": [],
                "external_action": [],
            },
        },
        "decision_ids": [],
        "existing_runtime_links": [],
        "source_dictionary_id": dictionary_id,
    }


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


def compile_runtime_projection(
    canonical_root: Path,
    output_root: Path,
    *,
    shard_size: int = 10000,
) -> dict[str, Any]:
    """Compile canonical dictionary records into current SemanticDataRuntime files."""
    if shard_size < 100:
        raise ValueError("shard-size must be at least 100")
    canonical_manifest = validate_compiled_dictionary_root(canonical_root)
    records = [project_record(item) for item in _iter_canonical_records(canonical_root)]
    records.sort(key=lambda item: item["record_id"])

    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    surface_index: dict[str, set[str]] = defaultdict(set)
    reading_index: dict[str, set[str]] = defaultdict(set)
    locator: dict[str, dict[str, int]] = {}
    for number, record in enumerate(records):
        record_id = record["record_id"]
        locator[record_id] = {
            "shard": number // shard_size,
            "line": number % shard_size + 1,
        }
        for value in record["normalized_surfaces"]:
            surface_index[normalize_key(value)].add(record_id)
        for value in record["readings"]:
            reading_index[normalize_key(value)].add(record_id)

    surface_values = {
        key: sorted(values) for key, values in sorted(surface_index.items())
    }
    reading_values = {
        key: sorted(values) for key, values in sorted(reading_index.items())
    }
    locator_values = dict(sorted(locator.items()))
    outputs: list[dict[str, Any]] = []
    indexes = {
        "runtime-surface-index.json.gz": surface_values,
        "runtime-reading-index.json.gz": reading_values,
        "runtime-record-locator.json.gz": locator_values,
        "surface-index.json.gz": surface_values,
        "reading-index.json.gz": reading_values,
        "record-locator.json.gz": locator_values,
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
        relative = f"records/records-{start // shard_size:04d}.jsonl.gz"
        meta = _write_gzip(output_root / relative, payload)
        meta["path"] = relative
        meta["record_count"] = len(selected)
        outputs.append(meta)

    manifest = {
        "schema_version": "2.0.0",
        "compiler_version": f"canonical-runtime-projection-{RUNTIME_PROJECTION_VERSION}",
        "mode": "approved-canonical-dictionary-runtime-projection",
        "record_count": len(records),
        "runtime_record_count": len(records),
        "reading_mapping_count": sum(
            len(record.get("reading_mappings") or []) for record in records
        ),
        "contextual_candidate_count": sum(
            1
            for record in records
            for candidate in record.get("meaning_candidates") or []
            if any(
                (candidate.get("context") or {}).get(key)
                for key in _CONTEXT_CONDITION_KEYS
            )
        ),
        "record_shard_size": shard_size,
        "record_shards": (
            (len(records) + shard_size - 1) // shard_size if records else 0
        ),
        "approved_only": True,
        "field_scope_projection": True,
        "preserve_ambiguity": True,
        "automatic_external_action": False,
        "canonical_dictionary_manifest_sha256": _sha256_file(
            canonical_root / "manifest.json"
        ),
        "canonical_dictionary_record_count": int(
            canonical_manifest.get("record_count", 0)
        ),
        "boundaries": {
            "source_is_mcp_canonical_dictionary": True,
            "meaning_re_resolution": False,
            "runtime_external_dictionary_lookup": False,
            "automatic_meaning_generation": False,
            "approved_meaning_only": True,
            "reading_mapping_projection": True,
            "sense_context_projection": True,
            "record_context_projection_is_common_only": True,
        },
        "outputs": outputs,
    }
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    validate_runtime_projection(output_root)
    return manifest


def validate_runtime_projection(root: Path) -> dict[str, Any]:
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("approved_only") is not True:
        raise ValueError("canonical runtime projection must be approved-only")
    if manifest.get("automatic_external_action") is not False:
        raise ValueError("canonical runtime projection external-action boundary invalid")
    if manifest.get("preserve_ambiguity") is not True:
        raise ValueError("canonical runtime projection must preserve ambiguity")
    boundaries = manifest.get("boundaries") or {}
    if boundaries.get("source_is_mcp_canonical_dictionary") is not True:
        raise ValueError("canonical runtime projection source boundary invalid")
    if boundaries.get("meaning_re_resolution") is not False:
        raise ValueError("canonical runtime projection must not re-resolve meaning")
    if boundaries.get("reading_mapping_projection") is not True:
        raise ValueError("canonical runtime projection reading mapping boundary invalid")
    if boundaries.get("sense_context_projection") is not True:
        raise ValueError("canonical runtime projection sense context boundary invalid")
    if boundaries.get("record_context_projection_is_common_only") is not True:
        raise ValueError("canonical runtime projection record context boundary invalid")
    required = {
        "runtime-surface-index.json.gz",
        "runtime-reading-index.json.gz",
        "runtime-record-locator.json.gz",
        "surface-index.json.gz",
        "reading-index.json.gz",
        "record-locator.json.gz",
    }
    missing = [
        name
        for name in sorted(required)
        if not (root / "indexes" / name).is_file()
    ]
    if missing:
        raise FileNotFoundError(
            "canonical runtime projection indexes incomplete: " + ", ".join(missing)
        )
    for output in manifest.get("outputs") or []:
        path = root / str(output.get("path") or "")
        if not path.is_file():
            raise FileNotFoundError(path)
        expected_sha = str(output.get("sha256") or "")
        if expected_sha and _sha256_file(path) != expected_sha:
            raise ValueError(f"canonical runtime projection digest mismatch: {path}")
    with gzip.open(
        root / "indexes/runtime-record-locator.json.gz", "rt", encoding="utf-8"
    ) as handle:
        locator = json.load(handle)
    if len(locator) != int(manifest.get("runtime_record_count", 0)):
        raise ValueError("canonical runtime projection locator count mismatch")
    return manifest
