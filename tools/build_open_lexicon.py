#!/usr/bin/env python3
"""Build a deterministic 100k+ approved base lexicon snapshot from trusted sources."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sys
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dictionary_supply.common import LexiconRecord, read_jsonl

TRUSTED_BASE_SOURCES = {
    ("JMdict", "CC-BY-SA-4.0"),
    ("SudachiDict", "Apache-2.0"),
    ("Wikidata Lexemes", "CC0-1.0"),
    (
        "Japanese Wiktionary",
        "CC-BY-SA-4.0 AND GFDL-1.3-or-later",
    ),
}


def license_bucket(license_expression: str) -> str:
    value = license_expression.upper()
    if "CC0" in value:
        return "cc0"
    if "APACHE" in value:
        return "apache-2.0"
    if "CC-BY-SA" in value or "CC BY-SA" in value:
        return "cc-by-sa"
    if "GPL" in value or "GFDL" in value or "LGPL" in value:
        return "copyleft-other"
    raise ValueError(f"unapproved base-lexicon license: {license_expression}")


def lexical_base_record(record: LexiconRecord) -> LexiconRecord:
    record.validate()
    source_key = (record.source.dataset, record.source.license)
    if source_key not in TRUSTED_BASE_SOURCES:
        raise ValueError(
            "source is not trusted for automatic lexical-base approval: "
            f"{source_key}"
        )
    if not record.source.source_sha256:
        raise ValueError(f"source checksum is required: {record.record_id}")

    # Automatic approval is limited to lexical identity information.
    # Definitions and semantic relations remain available only in proposal/review data.
    record.senses = []
    record.synonyms = []
    record.antonyms = []
    record.related = []
    record.forms = []
    record.review_status = "approved"
    record.notes = [
        *record.notes,
        "Automatically approved as lexical identity data only.",
        "No intent, task, metaphor, pragmatic meaning, or external action was auto-promoted.",
    ]
    return record.normalized()


def deduplicate(records: Iterable[LexiconRecord]) -> list[LexiconRecord]:
    by_key: dict[tuple, LexiconRecord] = {}
    for raw in records:
        record = lexical_base_record(raw)
        key = (
            record.lemma,
            tuple(sorted(record.readings)),
            tuple(sorted(record.part_of_speech)),
        )
        current = by_key.get(key)
        if current is None:
            by_key[key] = record
            continue
        for value in record.surfaces:
            if value not in current.surfaces:
                current.surfaces.append(value)
        current.notes.append(
            f"Merged lexical source record: {record.source.dataset}:{record.source.source_id}"
        )
        current.normalized()
    return sorted(
        by_key.values(),
        key=lambda item: (
            item.lemma,
            tuple(item.readings),
            tuple(item.part_of_speech),
            item.record_id,
        ),
    )


def write_shards(
    output_root: Path,
    *,
    batch_id: str,
    records: list[LexiconRecord],
    shard_size: int,
) -> tuple[list[dict], int]:
    shards: list[dict] = []
    total_bytes = 0
    by_bucket: dict[str, list[LexiconRecord]] = {}
    for record in records:
        bucket = license_bucket(record.source.license)
        by_bucket.setdefault(bucket, []).append(record)

    for bucket, bucket_records in sorted(by_bucket.items()):
        directory = output_root / bucket
        directory.mkdir(parents=True, exist_ok=True)
        for start in range(0, len(bucket_records), shard_size):
            number = start // shard_size + 1
            path = directory / f"{batch_id}-{number:04d}.jsonl.gz"
            if path.exists():
                raise ValueError(f"base lexicon shard already exists: {path}")
            selected = bucket_records[start : start + shard_size]
            digest = hashlib.sha256()
            with gzip.open(
                path,
                "wt",
                encoding="utf-8",
                newline="\n",
                compresslevel=9,
            ) as handle:
                for record in selected:
                    line = json.dumps(
                        record.to_dict(),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ) + "\n"
                    handle.write(line)
                    digest.update(line.encode("utf-8"))
            size = path.stat().st_size
            total_bytes += size
            shards.append({
                "path": str(path.relative_to(output_root.parent.parent.parent)),
                "license_bucket": bucket,
                "record_count": len(selected),
                "uncompressed_content_sha256": digest.hexdigest(),
                "compressed_bytes": size,
            })
    return shards, total_bytes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--minimum-records", type=int, default=100000)
    parser.add_argument("--maximum-records", type=int)
    parser.add_argument("--shard-size", type=int, default=10000)
    args = parser.parse_args()
    if args.minimum_records < 1:
        parser.error("minimum-records must be at least 1")
    if args.shard_size < 100:
        parser.error("shard-size must be at least 100")
    if (
        args.maximum_records is not None
        and args.maximum_records < args.minimum_records
    ):
        parser.error("maximum-records must be >= minimum-records")

    imported: list[LexiconRecord] = []
    for path in args.input:
        imported.extend(read_jsonl(path))
    records = deduplicate(imported)
    if args.maximum_records is not None:
        records = records[: args.maximum_records]
    if len(records) < args.minimum_records:
        raise RuntimeError(
            "open lexicon minimum was not reached: "
            f"required={args.minimum_records} actual={len(records)}"
        )

    shards, compressed_bytes = write_shards(
        args.output_root,
        batch_id=args.batch_id,
        records=records,
        shard_size=args.shard_size,
    )
    sources = Counter(
        (
            item.source.dataset,
            item.source.version,
            item.source.license,
            item.source.source_sha256,
        )
        for item in records
    )
    surface_count = sum(len(item.surfaces) for item in records)
    payload = {
        "schema_version": "1.0.0",
        "batch_id": args.batch_id,
        "mode": "trusted_lexical_identity_only",
        "record_count": len(records),
        "surface_count": surface_count,
        "minimum_record_contract": args.minimum_records,
        "compressed_bytes": compressed_bytes,
        "sources": [
            {
                "dataset": key[0],
                "version": key[1],
                "license": key[2],
                "source_sha256": key[3],
                "record_count": count,
            }
            for key, count in sorted(sources.items())
        ],
        "shards": shards,
        "semantic_auto_promotion": False,
        "external_action_auto_promotion": False,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "OPEN LEXICON BUILD OK: "
        f"records={len(records)} surfaces={surface_count} "
        f"shards={len(shards)} compressed_bytes={compressed_bytes}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
