#!/usr/bin/env python3
"""Build a deterministic 100k+ approved base lexicon snapshot from trusted sources."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import io
import json
from itertools import chain
from pathlib import Path
import re
import sys
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dictionary_supply.common import (
    LexiconRecord,
    read_jsonl,
    sha256_file,
)

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
    # Source importers must separate orthographic surfaces from readings.
    record.senses = []
    record.synonyms = []
    record.antonyms = []
    record.related = []
    record.forms = []
    record.review_status = "approved"
    record.notes = [
        *record.notes,
        "Automatically approved as lexical identity data only.",
        "Readings are metadata and are not canonical aliases.",
        (
            "No intent, task, metaphor, pragmatic meaning, or external action "
            "was auto-promoted."
        ),
    ]
    return record.normalized()


def deduplicate(
    records: Iterable[LexiconRecord],
    *,
    maximum_records: int | None = None,
) -> list[LexiconRecord]:
    by_key: dict[tuple, LexiconRecord] = {}
    for raw in records:
        record = lexical_base_record(raw)
        key = (
            record.source.dataset,
            record.source.source_id,
            record.lemma,
        )
        current = by_key.get(key)
        if current is None:
            by_key[key] = record
            if (
                maximum_records is not None
                and len(by_key) >= maximum_records
            ):
                break
            continue
        for value in record.surfaces:
            if value not in current.surfaces:
                current.surfaces.append(value)
        for value in record.readings:
            if value not in current.readings:
                current.readings.append(value)
        current.reading_mappings.extend(record.reading_mappings)
        current.notes.append(
            "Merged duplicate source record: "
            f"{record.source.dataset}:{record.source.source_id}"
        )
        current.normalized()
    return sorted(
        by_key.values(),
        key=lambda item: (
            item.source.dataset,
            item.source.source_id,
            item.lemma,
            item.record_id,
        ),
    )


def _write_deterministic_gzip(
    path: Path,
    records: list[LexiconRecord],
) -> str:
    digest = hashlib.sha256()
    with path.open("wb") as raw:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw,
            compresslevel=9,
            mtime=0,
        ) as compressed:
            with io.TextIOWrapper(
                compressed,
                encoding="utf-8",
                newline="\n",
            ) as handle:
                for record in records:
                    line = json.dumps(
                        record.to_dict(),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ) + "\n"
                    handle.write(line)
                    digest.update(line.encode("utf-8"))
    return digest.hexdigest()


def write_shards(
    output_root: Path,
    *,
    batch_id: str,
    records: list[LexiconRecord],
    shard_size: int,
    repo_root: Path | None = None,
) -> tuple[list[dict], int]:
    shards: list[dict] = []
    total_bytes = 0
    by_bucket: dict[str, list[LexiconRecord]] = {}
    for record in records:
        bucket = license_bucket(record.source.license)
        by_bucket.setdefault(bucket, []).append(record)

    root = (repo_root or output_root.parent.parent.parent).resolve()
    for bucket, bucket_records in sorted(by_bucket.items()):
        directory = output_root / bucket
        directory.mkdir(parents=True, exist_ok=True)
        for start in range(0, len(bucket_records), shard_size):
            number = start // shard_size + 1
            path = directory / f"{batch_id}-{number:04d}.jsonl.gz"
            if path.exists():
                raise ValueError(f"base lexicon shard already exists: {path}")
            selected = bucket_records[start : start + shard_size]
            content_digest = _write_deterministic_gzip(path, selected)
            size = path.stat().st_size
            total_bytes += size
            shards.append({
                "path": str(path.resolve().relative_to(root)),
                "license_bucket": bucket,
                "record_count": len(selected),
                "uncompressed_content_sha256": content_digest,
                "compressed_sha256": sha256_file(path),
                "compressed_bytes": size,
            })
    return shards, total_bytes


def sync_repository_metadata(
    repo_root: Path,
    *,
    batch_id: str,
    record_count: int,
) -> None:
    manifest_path = (
        repo_root
        / "dictionaries/system/metaphors/manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["open_lexicon_records"] = record_count
    manifest["open_lexicon_release_batch"] = batch_id
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    readme_path = repo_root / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    readme, changed = re.subn(
        r"(\| Open lexical records \| \*\*)\d+(\*\* \|)",
        rf"\g<1>{record_count}\g<2>",
        readme,
    )
    if changed != 2:
        raise ValueError(
            "README open lexical record markers must exist in Japanese and "
            f"English tables: changed={changed}"
        )
    readme = readme.replace(
        (
            "無料辞書資源のImporterと昇格Pipelineは実装済みですが、"
            "このCommitでは外部辞書の全Dumpを無審査でRepositoryへ"
            "収録していません。"
        ),
        (
            f"このRelease artifactには、信頼済みOpen SourceからBuildした"
            f"語彙識別専用Base Lexiconを{record_count}件収録しています。"
            "語義・Intent・Task・比喩・外部Actionは自動昇格していません。"
        ),
    )
    readme = readme.replace(
        (
            "At the current repository state, no external open-lexicon records "
            "have been promoted into the runtime packs."
        ),
        (
            f"This release artifact contains {record_count} trusted open lexical "
            "identity records. No sense, intent, task, metaphor, pragmatic "
            "meaning, or external action was auto-promoted."
        ),
    )
    readme_path.write_text(readme, encoding="utf-8")

    notice_path = repo_root / "NOTICE.md"
    notice = notice_path.read_text(encoding="utf-8")
    notice = notice.replace(
        (
            "At the current repository state, no external open-lexicon records "
            "have been promoted into the runtime packs."
        ),
        (
            f"Release batch `{batch_id}` contains {record_count} automatically "
            "approved lexical-identity records from trusted open sources. "
            "Semantic and executable meanings were not auto-promoted."
        ),
    )
    notice_path.write_text(notice, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--minimum-records", type=int, default=100000)
    parser.add_argument("--maximum-records", type=int)
    parser.add_argument("--shard-size", type=int, default=10000)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--sync-repository-metadata", action="store_true")
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

    stream = chain.from_iterable(read_jsonl(path) for path in args.input)
    records = deduplicate(
        stream,
        maximum_records=args.maximum_records,
    )
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
        repo_root=args.repo_root,
    )
    source_values: dict[tuple, dict] = {}
    source_counts: Counter[tuple] = Counter()
    for item in records:
        key = (
            item.source.dataset,
            item.source.version,
            item.source.license,
            item.source.source_sha256,
        )
        source_counts[key] += 1
        source_values[key] = {
            "dataset": item.source.dataset,
            "version": item.source.version,
            "license": item.source.license,
            "source_url": item.source.source_url,
            "source_sha256": item.source.source_sha256,
            "attribution": item.source.attribution,
        }
    surface_count = sum(len(item.surfaces) for item in records)
    payload = {
        "schema_version": "1.1.0",
        "batch_id": args.batch_id,
        "mode": "trusted_lexical_identity_only",
        "record_count": len(records),
        "surface_count": surface_count,
        "minimum_record_contract": args.minimum_records,
        "compressed_bytes": compressed_bytes,
        "sources": [
            {
                **source_values[key],
                "record_count": source_counts[key],
            }
            for key in sorted(source_values)
        ],
        "shards": shards,
        "reading_alias_promotion": False,
        "semantic_auto_promotion": False,
        "external_action_auto_promotion": False,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.sync_repository_metadata:
        sync_repository_metadata(
            args.repo_root,
            batch_id=args.batch_id,
            record_count=len(records),
        )
    print(
        "OPEN LEXICON BUILD OK: "
        f"records={len(records)} surfaces={surface_count} "
        f"shards={len(shards)} compressed_bytes={compressed_bytes}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
