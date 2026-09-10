"""Universal build-time source-adapter contract for the MCP dictionary factory.

Source-specific parsers emit adapter records into this contract. Source-authored
definitions/glosses are routed two ways: (1) semantic-reference evidence for resolving
existing words and (2) lexical candidates so newly discovered words can enter the MCP's
own review/decision pipeline. Classification, translation, familiarity, entity,
sentiment, syntax and other non-definition material becomes canonical auxiliary
evidence. This module never invents a definition and never auto-approves a candidate.
"""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
from typing import Any, Iterable, Iterator, TextIO
import unicodedata

from .canonical_evidence import ALLOWED_SOURCE_ROLES

ADAPTER_SCHEMA_VERSION = "1.2.0"
MEANING_ROLE = "lexical-definition"
ALLOWED_ADAPTER_ROLES = {MEANING_ROLE, *ALLOWED_SOURCE_ROLES}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    return [value]


def _normalize_text(value: Any) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def _stable_unique(values: Iterable[Any]) -> list[str]:
    return sorted({_normalize_text(value) for value in values if _normalize_text(value)})


def _reading_mappings(raw: dict[str, Any]) -> list[dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for value in _as_list(raw.get("reading_mappings")):
        if not isinstance(value, dict):
            continue
        reading = _normalize_text(value.get("reading"))
        if not reading:
            continue
        mapping = {
            "reading": reading,
            "restricted_to": _stable_unique(value.get("restricted_to") or []),
            "no_kanji": bool(value.get("no_kanji", False)),
        }
        output[_json_line(mapping)] = mapping
    return [output[key] for key in sorted(output)]


def _json_line(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_source(source: dict[str, Any], record_id: str) -> dict[str, Any]:
    required = ("dataset", "version", "license", "source_id", "source_sha256")
    missing = [key for key in required if not _normalize_text(source.get(key))]
    if missing:
        raise ValueError(f"adapter source fields required for {record_id}: {missing}")
    digest = _normalize_text(source.get("source_sha256")).lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError(f"adapter source_sha256 invalid for {record_id}")
    normalized = {
        "dataset": _normalize_text(source.get("dataset")),
        "version": _normalize_text(source.get("version")),
        "license": _normalize_text(source.get("license")),
        "source_id": _normalize_text(source.get("source_id")),
        "source_url": _normalize_text(source.get("source_url")),
        "source_sha256": digest,
        "attribution": _normalize_text(source.get("attribution")),
    }
    for key in (
        "logical_source_id",
        "source_record_id",
        "source_record_sha256",
        "payload_path",
        "payload_sha256",
        "rights_lane",
    ):
        value = _normalize_text(source.get(key))
        if value:
            normalized[key] = value
    for key in ("artifact_id", "workflow_run_id"):
        value = source.get(key)
        if value not in (None, ""):
            normalized[key] = int(value)
    for key in (
        "public_runtime_eligible", "source_meaning_complete", "license_metadata_complete",
    ):
        if key in source:
            normalized[key] = bool(source.get(key))
    for key in ("source_record_sha256", "payload_sha256"):
        if key in normalized:
            value = str(normalized[key]).lower()
            if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise ValueError(f"adapter {key} invalid for {record_id}")
            normalized[key] = value
    return normalized


def normalize_adapter_record(raw: dict[str, Any], *, path: Path, line: int) -> dict[str, Any]:
    record_id = _normalize_text(
        raw.get("adapter_record_id") or raw.get("record_id") or raw.get("id")
    )
    if not record_id:
        raise ValueError(f"adapter record id required: {path}:{line}")
    role = _normalize_text(raw.get("source_role") or raw.get("role"))
    if role not in ALLOWED_ADAPTER_ROLES:
        raise ValueError(f"adapter source_role invalid: {record_id}:{role}")
    surfaces = _stable_unique(
        [raw.get("surface"), raw.get("lemma"), *_as_list(raw.get("surfaces"))]
    )
    if not surfaces:
        raise ValueError(f"adapter surface required: {record_id}")
    reading_mappings = _reading_mappings(raw)
    readings = _stable_unique(
        [
            raw.get("reading"),
            *_as_list(raw.get("readings")),
            *(item["reading"] for item in reading_mappings),
        ]
    )
    pos = _stable_unique(
        [
            raw.get("part_of_speech"),
            raw.get("pos"),
            *_as_list(raw.get("part_of_speech_list")),
        ]
    )
    domains = _stable_unique([raw.get("domain"), *_as_list(raw.get("domains"))])
    source = raw.get("source") or {}
    if not isinstance(source, dict):
        raise ValueError(f"adapter source object required: {record_id}")
    source = _validate_source(source, record_id)

    meanings = _stable_unique(
        [
            raw.get("meaning"),
            raw.get("gloss"),
            *_as_list(raw.get("meanings")),
            *_as_list(raw.get("glosses")),
            *_as_list(raw.get("definitions")),
        ]
    )
    payload = raw.get("payload")
    if role == MEANING_ROLE:
        if not meanings:
            raise ValueError(
                f"lexical-definition adapter record requires source-authored meaning: {record_id}"
            )
        if payload not in (None, {}) and not isinstance(payload, dict):
            raise ValueError(f"adapter payload must be object: {record_id}")
    else:
        if meanings:
            raise ValueError(
                f"non-definition adapter role must not supply meanings: {record_id}:{role}"
            )
        if not isinstance(payload, dict) or not payload:
            raise ValueError(f"auxiliary adapter payload required: {record_id}")

    return {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "adapter_record_id": record_id,
        "source_role": role,
        "surfaces": surfaces,
        "readings": readings,
        "reading_mappings": reading_mappings,
        "part_of_speech": pos,
        "domains": domains,
        "meanings": meanings,
        "payload": payload or {},
        "source": source,
    }


def iter_adapter_records(
    paths: Iterable[Path], *, ordered_unique: bool = False
) -> Iterator[dict[str, Any]]:
    seen: set[str] = set()
    previous_id: str | None = None
    for path in sorted(set(paths), key=str):
        opener = gzip.open if path.name.endswith(".gz") else Path.open
        with opener(path, "rt", encoding="utf-8") as handle:  # type: ignore[arg-type]
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                raw = json.loads(line)
                if not isinstance(raw, dict):
                    raise ValueError(f"adapter row must be object: {path}:{line_number}")
                record = normalize_adapter_record(raw, path=path, line=line_number)
                record_id = record["adapter_record_id"]
                if ordered_unique:
                    if previous_id is not None and record_id <= previous_id:
                        raise ValueError(
                            "adapter records must be strictly ordered and unique: "
                            f"{previous_id}:{record_id}"
                        )
                    previous_id = record_id
                else:
                    if record_id in seen:
                        raise ValueError(f"duplicate adapter record id: {record_id}")
                    seen.add(record_id)
                yield record


@contextmanager
def _text_output(path: Path, *, compressed: bool) -> Iterator[TextIO]:
    if not compressed:
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            yield handle
        return
    with path.open("wb") as raw:
        with gzip.GzipFile(
            filename="", mode="wb", fileobj=raw, compresslevel=6, mtime=0
        ) as zipped:
            with io.TextIOWrapper(zipped, encoding="utf-8", newline="\n") as handle:
                yield handle


def semantic_reference_row(record: dict[str, Any]) -> dict[str, Any]:
    if record["source_role"] != MEANING_ROLE:
        raise ValueError("semantic_reference_row requires lexical-definition role")
    source = record["source"]
    return {
        "id": record["adapter_record_id"],
        "source_id": source["source_id"],
        "surface": record["surfaces"][0],
        "surfaces": record["surfaces"],
        "readings": record["readings"],
        "reading_mappings": record["reading_mappings"],
        "part_of_speech": record["part_of_speech"],
        "domains": record["domains"],
        "meanings": record["meanings"],
        "dataset": source["dataset"],
        "version": source["version"],
        "license": source["license"],
        "source_url": source["source_url"],
        "source_sha256": source["source_sha256"],
        "attribution": source["attribution"],
        "source": source,
        "meaning_origin": "source-authored",
        "automatic_approval": False,
    }


def lexical_candidate_row(record: dict[str, Any]) -> dict[str, Any]:
    """Create a new-word candidate for the MCP-owned dictionary review lane."""
    if record["source_role"] != MEANING_ROLE:
        raise ValueError("lexical_candidate_row requires lexical-definition role")
    source = record["source"]
    adapter_id = record["adapter_record_id"]
    candidates = [
        {
            "candidate_id": f"{adapter_id}:source-sense:{index:03d}",
            "label": meaning,
            "glosses": [meaning],
            "part_of_speech": record["part_of_speech"],
            "domains": record["domains"],
            "parameters": {},
            "register": {},
            "context": {},
            "evidence_ids": [f"source:{source['source_id']}"],
            "review_status": "needs-evidence",
            "meaning_source": "source-authored-adapter-record",
        }
        for index, meaning in enumerate(record["meanings"], 1)
    ]
    return {
        "record_id": f"ADAPTER-{adapter_id}",
        "source_kind": "open_lexicon",
        "lemma": record["surfaces"][0],
        "surfaces": record["surfaces"],
        "readings": record["readings"],
        "reading_mappings": record["reading_mappings"],
        "part_of_speech": record["part_of_speech"],
        "domains": record["domains"],
        "meaning_candidates": candidates,
        "semantic_targets": ["lexicon"],
        "review_status": "needs-evidence",
        "approval_scopes": {
            "lexical": "needs-evidence",
            "semantic": "needs-evidence",
            "pragmatic": "needs-evidence",
            "task": "needs-evidence",
            "external_action": "needs-evidence",
        },
        "source": {
            **source,
            "evidence_scope": "dictionary_source_candidate",
        },
        "adapter_record_id": adapter_id,
        "automatic_approval": False,
        "automatic_runtime_promotion": False,
    }


def canonical_evidence_row(record: dict[str, Any]) -> dict[str, Any]:
    if record["source_role"] == MEANING_ROLE:
        raise ValueError("canonical_evidence_row requires auxiliary role")
    return {
        "schema_version": "1.0.0",
        "evidence_id": record["adapter_record_id"],
        "source_role": record["source_role"],
        "surfaces": record["surfaces"],
        "readings": record["readings"],
        "reading_mappings": record["reading_mappings"],
        "part_of_speech_list": record["part_of_speech"],
        "payload": record["payload"],
        "source": record["source"],
        "automatic_meaning_generation": False,
    }


def compile_adapter_contract(
    input_paths: Iterable[Path],
    output_root: Path,
    *,
    compressed: bool = False,
    ordered_unique: bool = False,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    suffix = ".jsonl.gz" if compressed else ".jsonl"
    semantic_path = output_root / f"semantic-reference{suffix}"
    lexical_path = output_root / f"lexical-candidates{suffix}"
    evidence_path = output_root / f"canonical-evidence{suffix}"
    role_counts: Counter[str] = Counter()
    counts: Counter[str] = Counter()
    with (
        _text_output(semantic_path, compressed=compressed) as semantic,
        _text_output(lexical_path, compressed=compressed) as lexical,
        _text_output(evidence_path, compressed=compressed) as evidence,
    ):
        for record in iter_adapter_records(input_paths, ordered_unique=ordered_unique):
            counts["adapter"] += 1
            role_counts[record["source_role"]] += 1
            if record["source_role"] == MEANING_ROLE:
                semantic.write(_json_line(semantic_reference_row(record)) + "\n")
                lexical.write(_json_line(lexical_candidate_row(record)) + "\n")
                counts["semantic_reference"] += 1
                counts["lexical_candidate"] += 1
            else:
                evidence.write(_json_line(canonical_evidence_row(record)) + "\n")
                counts["canonical_evidence"] += 1
    manifest = {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "mode": "mcp-universal-source-adapter-contract",
        "adapter_record_count": counts["adapter"],
        "semantic_reference_record_count": counts["semantic_reference"],
        "lexical_candidate_record_count": counts["lexical_candidate"],
        "canonical_evidence_record_count": counts["canonical_evidence"],
        "source_role_counts": dict(sorted(role_counts.items())),
        "boundaries": {
            "source_authored_definition_required_for_meaning_reference": True,
            "definition_sources_create_new_word_candidates": True,
            "new_word_candidates_require_decision_ledger_review": True,
            "auxiliary_evidence_never_becomes_definition": True,
            "automatic_approval": False,
            "runtime_promotion": False,
        },
        "outputs": {
            semantic_path.name: {
                "bytes": semantic_path.stat().st_size,
                "sha256": _sha256_file(semantic_path),
            },
            lexical_path.name: {
                "bytes": lexical_path.stat().st_size,
                "sha256": _sha256_file(lexical_path),
            },
            evidence_path.name: {
                "bytes": evidence_path.stat().st_size,
                "sha256": _sha256_file(evidence_path),
            },
        },
    }
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", type=Path, nargs="+")
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    manifest = compile_adapter_contract(args.inputs, args.output_root)
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
