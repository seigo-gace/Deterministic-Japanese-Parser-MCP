#!/usr/bin/env python3
"""Compile reviewed open-lexicon JSONL shards into deterministic runtime indexes.

This compiler does not infer senses, intents, tasks, pragmatic meanings, or
external actions. It preserves lexical identity, orthographic surfaces,
readings and their restrictions, part-of-speech, domain, usage, provenance,
and same-surface ambiguity.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dictionary_supply.common import LexiconRecord, read_jsonl, sha256_file

SCHEMA_VERSION = "1.0.0"
SEMANTIC_FIELDS = ("senses", "forms", "synonyms", "antonyms", "related")


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _write_gzip_bytes(path: Path, payload: bytes) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw,
            compresslevel=9,
            mtime=0,
        ) as gz:
            gz.write(payload)
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "uncompressed_sha256": hashlib.sha256(payload).hexdigest(),
        "uncompressed_bytes": len(payload),
    }


def _write_json_gzip(path: Path, value: Any) -> dict[str, Any]:
    return _write_gzip_bytes(path, _json_bytes(value))


def _write_jsonl_gzip(path: Path, rows: Iterable[dict[str, Any]]) -> tuple[dict[str, Any], int]:
    payload = b"".join(_json_bytes(row) for row in rows)
    meta = _write_gzip_bytes(path, payload)
    return meta, payload.count(b"\n")


def _source_shards(root: Path) -> list[Path]:
    return sorted(
        [*root.rglob("*.jsonl"), *root.rglob("*.jsonl.gz")],
        key=lambda p: str(p),
    )


def _stable_list(values: Iterable[str]) -> list[str]:
    return sorted(set(values))


def _minimal_record(record: LexiconRecord) -> dict[str, Any]:
    source = record.source
    assert source is not None
    return {
        "record_id": record.record_id,
        "lemma": record.lemma,
        "surfaces": list(record.surfaces),
        "readings": list(record.readings),
        "reading_mappings": list(record.reading_mappings),
        "part_of_speech": list(record.part_of_speech),
        "lexical_category": record.lexical_category,
        "domains": list(record.domains),
        "usage_labels": list(record.usage_labels),
        "source": {
            "dataset": source.dataset,
            "version": source.version,
            "license": source.license,
            "source_id": source.source_id,
            "source_url": source.source_url,
            "source_sha256": source.source_sha256,
            "attribution": source.attribution,
        },
        "review_status": record.review_status,
    }


def compile_runtime(
    *,
    input_root: Path,
    output_root: Path,
    expected_records: int,
    record_shard_size: int,
) -> dict[str, Any]:
    if expected_records < 1:
        raise ValueError("expected_records must be positive")
    if record_shard_size < 100:
        raise ValueError("record_shard_size must be at least 100")

    input_paths = _source_shards(input_root)
    if not input_paths:
        raise RuntimeError(f"no lexicon shards found under {input_root}")

    records: list[LexiconRecord] = []
    seen_record_ids: set[str] = set()
    input_manifest: list[dict[str, Any]] = []
    source_versions: set[str] = set()
    source_licenses: set[str] = set()

    for path in input_paths:
        shard_count = 0
        for record in read_jsonl(path):
            record.validate()
            if record.record_id in seen_record_ids:
                raise ValueError(f"duplicate record_id: {record.record_id}")
            if record.review_status != "approved":
                raise ValueError(
                    f"runtime source contains unapproved record: {record.record_id}"
                )
            for field in SEMANTIC_FIELDS:
                if getattr(record, field):
                    raise ValueError(
                        f"semantic field auto-promotion is forbidden: "
                        f"record={record.record_id} field={field}"
                    )
            if record.source is None or not record.source.source_sha256:
                raise ValueError(f"source checksum missing: {record.record_id}")
            seen_record_ids.add(record.record_id)
            source_versions.add(record.source.version)
            source_licenses.add(record.source.license)
            records.append(record)
            shard_count += 1
        input_manifest.append(
            {
                "path": str(path),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
                "record_count": shard_count,
            }
        )

    if len(records) != expected_records:
        raise RuntimeError(
            f"record contract failed: expected={expected_records} actual={len(records)}"
        )

    records.sort(key=lambda r: (r.record_id, r.lemma))

    canonical_groups: dict[str, set[str]] = defaultdict(set)
    surface_index: dict[str, set[str]] = defaultdict(set)
    reading_index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    pos_index: dict[str, set[str]] = defaultdict(set)
    domain_index: dict[str, set[str]] = defaultdict(set)
    usage_index: dict[str, set[str]] = defaultdict(set)
    record_locator: dict[str, dict[str, int]] = {}

    for record_number, record in enumerate(records):
        record_shard = record_number // record_shard_size
        record_line = record_number % record_shard_size + 1
        record_locator[record.record_id] = {
            "shard": record_shard,
            "line": record_line,
        }

        for surface in [record.lemma, *record.surfaces]:
            if not surface:
                continue
            canonical_groups[record.lemma].add(surface)
            surface_index[surface].add(record.record_id)

        mappings = list(record.reading_mappings)
        mapped_readings = {item.get("reading") for item in mappings}
        for reading in record.readings:
            if reading and reading not in mapped_readings:
                mappings.append(
                    {
                        "reading": reading,
                        "restricted_to": [],
                        "no_kanji": False,
                    }
                )
        for mapping in mappings:
            reading = str(mapping.get("reading", ""))
            if not reading:
                continue
            reading_index[reading].append(
                {
                    "record_id": record.record_id,
                    "restricted_to": list(mapping.get("restricted_to", [])),
                    "no_kanji": bool(mapping.get("no_kanji", False)),
                }
            )

        for value in record.part_of_speech:
            pos_index[value].add(record.record_id)
        if record.lexical_category:
            pos_index[f"lexical:{record.lexical_category}"].add(record.record_id)
        for value in record.domains:
            domain_index[value].add(record.record_id)
        for value in record.usage_labels:
            usage_index[value].add(record.record_id)

    canonical_groups_out = {
        key: _stable_list(values) for key, values in sorted(canonical_groups.items())
    }
    surface_index_out = {
        key: _stable_list(values) for key, values in sorted(surface_index.items())
    }
    reading_index_out = {
        key: sorted(
            values,
            key=lambda item: (
                item["record_id"],
                tuple(item["restricted_to"]),
                item["no_kanji"],
            ),
        )
        for key, values in sorted(reading_index.items())
    }
    homograph_index_out = {
        key: values
        for key, values in surface_index_out.items()
        if len(values) > 1
    }
    pos_index_out = {
        key: _stable_list(values) for key, values in sorted(pos_index.items())
    }
    domain_index_out = {
        key: _stable_list(values) for key, values in sorted(domain_index.items())
    }
    usage_index_out = {
        key: _stable_list(values) for key, values in sorted(usage_index.items())
    }

    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    outputs: list[dict[str, Any]] = []
    for filename, value in (
        ("indexes/canonical-groups.json.gz", canonical_groups_out),
        ("indexes/surface-index.json.gz", surface_index_out),
        ("indexes/reading-index.json.gz", reading_index_out),
        ("indexes/homograph-index.json.gz", homograph_index_out),
        ("indexes/pos-index.json.gz", pos_index_out),
        ("indexes/domain-index.json.gz", domain_index_out),
        ("indexes/usage-index.json.gz", usage_index_out),
        ("indexes/record-locator.json.gz", dict(sorted(record_locator.items()))),
    ):
        metadata = _write_json_gzip(output_root / filename, value)
        metadata["path"] = filename
        outputs.append(metadata)

    record_outputs: list[dict[str, Any]] = []
    for start in range(0, len(records), record_shard_size):
        number = start // record_shard_size
        selected = records[start : start + record_shard_size]
        relative = f"records/records-{number:04d}.jsonl.gz"
        metadata, count = _write_jsonl_gzip(
            output_root / relative,
            (_minimal_record(record) for record in selected),
        )
        metadata["path"] = relative
        metadata["record_count"] = count
        record_outputs.append(metadata)
        outputs.append(metadata)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "mode": "compiled_lexical_identity_only",
        "record_count": len(records),
        "expected_record_count": expected_records,
        "input_shard_count": len(input_paths),
        "input_shards": input_manifest,
        "source_versions": sorted(source_versions),
        "source_licenses": sorted(source_licenses),
        "unique_lemmas": len(canonical_groups_out),
        "unique_surfaces": len(surface_index_out),
        "unique_readings": len(reading_index_out),
        "homograph_surfaces": len(homograph_index_out),
        "part_of_speech_keys": len(pos_index_out),
        "domain_keys": len(domain_index_out),
        "usage_keys": len(usage_index_out),
        "record_shard_size": record_shard_size,
        "record_shards": len(record_outputs),
        "exact_lookup_only": True,
        "reading_alias_promotion": False,
        "semantic_auto_promotion": False,
        "intent_auto_promotion": False,
        "external_action_auto_promotion": False,
        "outputs": outputs,
    }
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--expected-records", type=int, default=120000)
    parser.add_argument("--record-shard-size", type=int, default=10000)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    manifest = compile_runtime(
        input_root=args.input_root,
        output_root=args.output_root,
        expected_records=args.expected_records,
        record_shard_size=args.record_shard_size,
    )
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
