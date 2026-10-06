"""Compile the canonical dictionary into Japanese-function projection metadata.

This is a build-time compiler.  It never creates lexical meaning.  Lane membership
is derived only from fields that are already present in the canonical record.
Unknown fields are preserved in an auditable queue instead of being silently
ignored.
"""
from __future__ import annotations

from collections.abc import Iterable
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
from typing import Any

from .canonical_dictionary import validate_compiled_dictionary_root


PROJECTION_SCHEMA_VERSION = "2.0.0"
PROJECTION_POLICY_VERSION = "japanese-function-projection-v2"
SCORING_POLICY_VERSION = "japanese-function-ranking-v1"

LANES = (
    "Orthography/Reading",
    "Noun-Entity",
    "Predicate-Inflection",
    "Function Words",
    "Connective-Modifier",
    "Onomatopoeia",
    "Multiword",
    "Syntax-Case-Clause",
    "Sense-Semantic Relation",
    "Usage-Context-Pragmatics",
    "Document Structure",
    "Evidence-Provenance-Rights",
)
LANE_BITS = {lane: 1 << index for index, lane in enumerate(LANES)}


def lane_mask_for(lanes: Iterable[str]) -> int:
    mask = 0
    for lane in lanes:
        mask |= LANE_BITS[lane]
    return mask

_POS_RULES: dict[str, tuple[str, ...]] = {
    "Noun-Entity": ("noun", "proper noun", "pronoun", "名詞", "代名詞", "固有名詞"),
    "Predicate-Inflection": ("verb", "adjective", "adjectival", "動詞", "形容詞", "形状詞"),
    "Function Words": ("particle", "auxiliary", "助詞", "助動詞", "接頭辞", "接尾辞"),
    "Connective-Modifier": ("conjunction", "adverb", "prenominal", "接続詞", "副詞", "連体詞"),
}

_EXPLICIT_TARGET_RULES: dict[str, tuple[str, ...]] = {
    "Noun-Entity": ("entity", "named-entity", "mention"),
    "Predicate-Inflection": ("predicate", "inflection", "morphology"),
    "Function Words": ("function-word", "particle", "auxiliary"),
    "Connective-Modifier": ("connective", "modifier"),
    "Onomatopoeia": ("onomatopoeia", "mimetic"),
    "Multiword": ("multiword", "idiom", "compound", "fixed-expression"),
    "Syntax-Case-Clause": ("syntax", "case", "clause", "dependency", "predicate-argument"),
    "Sense-Semantic Relation": ("lexicon", "sense", "semantic-relation", "lexical-relation"),
    "Usage-Context-Pragmatics": ("usage", "context", "pragmatics"),
    "Document Structure": ("document", "document-structure", "argumentation", "discourse-structure"),
}

_EXPLICIT_LABEL_RULES: dict[str, tuple[str, ...]] = {
    "Onomatopoeia": ("onomatopoe", "mimetic", "擬音", "擬態"),
    "Multiword": ("multiword", "idiom", "compound", "fixed expression", "熟語", "慣用"),
}

_KNOWN_TOP_LEVEL_FIELDS = frozenset({
    "dictionary_id",
    "lemma",
    "surfaces",
    "normalized_surfaces",
    "readings",
    "reading_mappings",
    "part_of_speech",
    "morphology",
    "domains",
    "senses",
    "pragmatics",
    "semantic_facets",
    "auxiliary_evidence",
    "source_evidence",
    "source_records",
    "source",
    "approval",
    "runtime_eligible",
    "decision_ids",
    "existing_runtime_links",
})


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _stable_strings(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip() for value in values if str(value).strip()}))


def _flatten_text(value: Any) -> tuple[str, ...]:
    if isinstance(value, dict):
        return _stable_strings(
            text
            for item in value.values()
            for text in _flatten_text(item)
        )
    if isinstance(value, (list, tuple, set)):
        return _stable_strings(text for item in value for text in _flatten_text(item))
    if value is None:
        return ()
    return (str(value).strip(),) if str(value).strip() else ()


def _semantic_targets(record: dict[str, Any]) -> tuple[str, ...]:
    facets = record.get("semantic_facets") or {}
    values = facets.get("semantic_targets") or [] if isinstance(facets, dict) else []
    return tuple(value.casefold() for value in _stable_strings(values))


def _pos_text(record: dict[str, Any]) -> str:
    return " ".join(_flatten_text(record.get("part_of_speech") or [])).casefold()


def _label_text(record: dict[str, Any]) -> str:
    values: list[str] = []
    values.extend(_flatten_text((record.get("semantic_facets") or {}).get("usage_labels") or []))
    for sense in record.get("senses") or []:
        if isinstance(sense, dict):
            values.extend(_flatten_text(sense.get("labels") or []))
    return " ".join(values).casefold()


def _has_nonempty(record: dict[str, Any], *keys: str) -> bool:
    return any(bool(record.get(key)) for key in keys)


def assign_record_lanes(record: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    """Return deterministic lane membership with inspectable evidence reasons."""
    reasons: dict[str, list[str]] = {lane: [] for lane in LANES}

    if _has_nonempty(record, "lemma", "surfaces", "normalized_surfaces", "readings", "reading_mappings"):
        reasons["Orthography/Reading"].append("orthography_or_reading_field")

    pos_text = _pos_text(record)
    for lane, markers in _POS_RULES.items():
        if any(marker.casefold() in pos_text for marker in markers):
            reasons[lane].append("part_of_speech")

    morphology = record.get("morphology") or {}
    if isinstance(morphology, dict) and any(bool(morphology.get(key)) for key in ("forms", "conjugation", "inflections")):
        reasons["Predicate-Inflection"].append("morphology")

    targets = set(_semantic_targets(record))
    for lane, markers in _EXPLICIT_TARGET_RULES.items():
        if any(marker in targets for marker in markers):
            reasons[lane].append("semantic_target")

    label_text = _label_text(record)
    for lane, markers in _EXPLICIT_LABEL_RULES.items():
        if any(marker.casefold() in label_text for marker in markers):
            reasons[lane].append("explicit_usage_or_sense_label")

    if record.get("senses"):
        reasons["Sense-Semantic Relation"].append("approved_sense")
    auxiliary = record.get("auxiliary_evidence") or {}
    if isinstance(auxiliary, dict) and any(key in auxiliary for key in ("lexical-relation", "semantic-class")):
        reasons["Sense-Semantic Relation"].append("typed_relation_evidence")

    pragmatics = record.get("pragmatics") or {}
    if pragmatics or (record.get("semantic_facets") or {}).get("usage_labels"):
        reasons["Usage-Context-Pragmatics"].append("pragmatic_or_usage_field")
    if any(isinstance(sense, dict) and sense.get("context") for sense in record.get("senses") or []):
        reasons["Usage-Context-Pragmatics"].append("sense_context")

    source_evidence_present = bool(record.get("source_evidence") or record.get("source_records") or record.get("source"))
    if not source_evidence_present:
        source_evidence_present = any(
            isinstance(sense, dict) and bool(sense.get("source_evidence"))
            for sense in record.get("senses") or []
        )
    if source_evidence_present or record.get("approval"):
        reasons["Evidence-Provenance-Rights"].append("source_or_approval_evidence")

    return {
        lane: tuple(sorted(set(values)))
        for lane, values in reasons.items()
        if values
    }


def _iter_canonical_records(root: Path) -> Iterable[dict[str, Any]]:
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
                    raise ValueError(f"canonical dictionary row must be object: {path}:{line_number}")
                yield value


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=DELETE")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(
        """
        CREATE TABLE bundle_metadata(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        ) WITHOUT ROWID;
        CREATE TABLE record_projection(
            record_id TEXT PRIMARY KEY,
            lane_mask INTEGER NOT NULL CHECK(lane_mask > 0)
        ) WITHOUT ROWID;
        CREATE TABLE rejected_record(
            record_id TEXT PRIMARY KEY,
            reason TEXT NOT NULL
        ) WITHOUT ROWID;
        CREATE TABLE unmapped_field_summary(
            field_name TEXT PRIMARY KEY,
            record_count INTEGER NOT NULL CHECK(record_count > 0)
        ) WITHOUT ROWID;
        CREATE TEMP TABLE record_identity(
            identity_sha256 TEXT PRIMARY KEY,
            canonical_record_id TEXT NOT NULL UNIQUE
        ) WITHOUT ROWID;
        CREATE TABLE duplicate_record(
            duplicate_record_id TEXT PRIMARY KEY,
            canonical_record_id TEXT NOT NULL,
            identity_sha256 TEXT NOT NULL
        ) WITHOUT ROWID;
        """
    )
    return connection


def validate_projection_bundle(root: Path) -> dict[str, Any]:
    manifest_path = root / "manifest.json"
    database_path = root / "projection.sqlite3"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    if not database_path.is_file():
        raise FileNotFoundError(database_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required = {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "projection_policy_version": PROJECTION_POLICY_VERSION,
        "scoring_policy_version": SCORING_POLICY_VERSION,
    }
    for key, expected in required.items():
        if manifest.get(key) != expected:
            raise ValueError(f"projection bundle compatibility mismatch: {key}")
    if tuple(manifest.get("lanes") or ()) != LANES:
        raise ValueError("projection bundle lane contract mismatch")
    expected_digest = str((manifest.get("outputs") or {}).get("projection.sqlite3", {}).get("sha256") or "")
    if not expected_digest or _sha256_file(database_path) != expected_digest:
        raise ValueError("projection bundle database digest mismatch")
    connection = sqlite3.connect(f"file:{database_path.resolve().as_posix()}?mode=ro&immutable=1", uri=True)
    try:
        projected = int(connection.execute("SELECT COUNT(*) FROM record_projection").fetchone()[0])
        rejected = int(connection.execute("SELECT COUNT(*) FROM rejected_record").fetchone()[0])
        duplicates = int(connection.execute("SELECT COUNT(*) FROM duplicate_record").fetchone()[0])
        unmapped = int(
            connection.execute(
                "SELECT COALESCE(SUM(record_count),0) FROM unmapped_field_summary"
            ).fetchone()[0]
        )
        lane_counts = {
            lane: int(
                connection.execute(
                    "SELECT COUNT(*) FROM record_projection WHERE (lane_mask & ?) != 0",
                    (bit,),
                ).fetchone()[0]
            )
            for lane, bit in LANE_BITS.items()
        }
        memberships = sum(lane_counts.values())
    finally:
        connection.close()
    if projected != int(manifest.get("projected_record_count", -1)):
        raise ValueError("projection bundle projected record count mismatch")
    if rejected != int(manifest.get("rejected_record_count", -1)):
        raise ValueError("projection bundle rejected record count mismatch")
    if memberships != int(manifest.get("lane_membership_count", -1)):
        raise ValueError("projection bundle membership count mismatch")
    if lane_counts != dict(manifest.get("lane_counts") or {}):
        raise ValueError("projection bundle lane count mismatch")
    if unmapped != int(manifest.get("unmapped_field_count", -1)):
        raise ValueError("projection bundle unmapped field count mismatch")
    if duplicates != int(manifest.get("duplicate_record_count", 0)):
        raise ValueError("projection bundle duplicate record count mismatch")
    source_count = int(manifest.get("canonical_record_count", -1))
    if projected + rejected + duplicates != source_count:
        raise ValueError("projection bundle conservation mismatch")
    return manifest


def compile_japanese_function_projection(canonical_root: Path, output_root: Path) -> dict[str, Any]:
    """Compile a scalable SQLite projection bundle and switch it atomically."""
    canonical_root = Path(canonical_root)
    output_root = Path(output_root)
    canonical_manifest = validate_compiled_dictionary_root(canonical_root)
    canonical_manifest_path = canonical_root / "manifest.json"
    staging = output_root.with_name(output_root.name + ".staging")
    backup = output_root.with_name(output_root.name + ".rollback")
    for path in (staging, backup):
        if path.exists():
            shutil.rmtree(path)
    staging.mkdir(parents=True)
    database_path = staging / "projection.sqlite3"
    connection = _connect(database_path)
    source_count = 0
    projected_count = 0
    rejected_count = 0
    membership_count = 0
    unmapped_count = 0
    unmapped_field_counts: dict[str, int] = {}
    lane_counts = {lane: 0 for lane in LANES}
    try:
        for record in _iter_canonical_records(canonical_root):
            source_count += 1
            record_id = str(record.get("dictionary_id") or "").strip()
            if not record_id:
                synthetic_id = f"missing-id:{source_count:012d}"
                connection.execute(
                    "INSERT INTO rejected_record(record_id,reason) VALUES(?,?)",
                    (synthetic_id, "missing_dictionary_id"),
                )
                rejected_count += 1
                continue
            lanes = assign_record_lanes(record)
            if not lanes:
                connection.execute(
                    "INSERT INTO rejected_record(record_id,reason) VALUES(?,?)",
                    (record_id, "no_supported_projection_lane"),
                )
                rejected_count += 1
            else:
                projected_count += 1
                connection.execute(
                    "INSERT INTO record_projection(record_id,lane_mask) VALUES(?,?)",
                    (record_id, lane_mask_for(lanes)),
                )
                membership_count += len(lanes)
                for lane in lanes:
                    lane_counts[lane] += 1
            for field_name in sorted(set(record) - _KNOWN_TOP_LEVEL_FIELDS):
                unmapped_field_counts[field_name] = unmapped_field_counts.get(field_name, 0) + 1
                unmapped_count += 1
        connection.executemany(
            "INSERT INTO unmapped_field_summary(field_name,record_count) VALUES(?,?)",
            sorted(unmapped_field_counts.items()),
        )
        metadata = {
            "schema_version": PROJECTION_SCHEMA_VERSION,
            "projection_policy_version": PROJECTION_POLICY_VERSION,
            "scoring_policy_version": SCORING_POLICY_VERSION,
            "canonical_manifest_sha": _sha256_file(canonical_manifest_path),
        }
        connection.executemany(
            "INSERT INTO bundle_metadata(key,value) VALUES(?,?)",
            sorted(metadata.items()),
        )
        connection.commit()
        connection.execute("VACUUM")
    finally:
        connection.close()

    manifest = {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "projection_policy_version": PROJECTION_POLICY_VERSION,
        "scoring_policy_version": SCORING_POLICY_VERSION,
        "canonical_manifest_sha": _sha256_file(canonical_manifest_path),
        "canonical_record_count": int(canonical_manifest.get("record_count", source_count)),
        "observed_canonical_record_count": source_count,
        "projected_record_count": projected_count,
        "rejected_record_count": rejected_count,
        "lane_membership_count": membership_count,
        "unmapped_field_count": unmapped_count,
        "duplicate_record_count": 0,
        "lanes": list(LANES),
        "lane_counts": lane_counts,
        "boundaries": {
            "canonical_dictionary_is_authority": True,
            "meaning_generation": False,
            "unknown_field_preservation": True,
            "unknown_field_audit_mode": "field-count-summary",
            "unknown_field_payload_duplication": False,
            "rejected_record_preservation": True,
            "rejected_payload_duplication": False,
            "deterministic_lane_assignment": True,
            "storage_model": "single-record-lane-bitmask-v1",
            "build_identity_persisted": False,
        },
        "outputs": {
            "projection.sqlite3": {
                "sha256": _sha256_file(database_path),
                "bytes": database_path.stat().st_size,
            }
        },
    }
    if source_count != int(canonical_manifest.get("record_count", source_count)):
        raise ValueError(
            f"canonical source count mismatch: manifest={canonical_manifest.get('record_count')} observed={source_count}"
        )
    (staging / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    validate_projection_bundle(staging)

    moved_old = False
    try:
        if output_root.exists():
            os.replace(output_root, backup)
            moved_old = True
        os.replace(staging, output_root)
    except Exception:
        if moved_old and backup.exists() and not output_root.exists():
            os.replace(backup, output_root)
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup)
    return validate_projection_bundle(output_root)
