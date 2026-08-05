#!/usr/bin/env python3
"""Compile review-pending meanings into a read-only SQLite candidate index.

Candidate-only records may be searched and exposed as MeaningGraph sense
candidates. They cannot select a sense, apply pragmatic parameters, create a
task, or authorize an external action.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
from typing import Any

STRUCTURAL_BLOCKERS = {
    "license-required",
    "source-dataset-required",
    "source-version-required",
    "source-digest-required",
    "reading-required",
    "part-of-speech-required",
    "meaning-candidate-required",
}
PLACEHOLDER_MARKERS = (
    "意味・機能はevidence確認待ち",
    "意味・機能は確認待ち",
    "source確認待ち",
    "meaning candidate from wiktionary-derived data; review required",
)
DB_NAME = "semantic-candidates.sqlite3"


def json_text(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def normalize_key(value: Any) -> str:
    return "".join(str(value or "").casefold().split())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            item = json.loads(line)
            if not isinstance(item, dict):
                raise ValueError(f"record must be an object: {path}:{line_number}")
            yield item


def meaningful_candidate(candidate: dict[str, Any]) -> bool:
    if candidate.get("candidate_kind") == "unresolved-shell":
        return False
    text = " ".join(
        str(candidate.get(key) or "")
        for key in ("label", "meaning", "interpretation", "gloss")
    ).casefold()
    if not text.strip():
        text = " ".join(
            str(value) for value in candidate.get("glosses") or []
        ).casefold()
    return bool(text.strip()) and not any(
        marker in text for marker in PLACEHOLDER_MARKERS
    )


def compact_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": candidate["candidate_id"],
        "label": (
            candidate.get("label")
            or candidate.get("meaning")
            or candidate.get("interpretation")
            or candidate.get("gloss")
            or next(iter(candidate.get("glosses") or []), candidate["candidate_id"])
        ),
        "glosses": list(candidate.get("glosses") or []),
        "part_of_speech": list(candidate.get("part_of_speech") or []),
        "domains": list(candidate.get("domains") or []),
        "evidence_ids": list(candidate.get("evidence_ids") or []),
        "review_status": candidate.get("review_status", "needs-evidence"),
    }


def candidate_record(record: dict[str, Any]) -> dict[str, Any] | None:
    if record.get("review_status") in {"rejected", "hold"}:
        return None
    blockers = set(record.get("review_blockers") or [])
    if blockers.intersection(STRUCTURAL_BLOCKERS):
        return None
    candidates = [
        compact_candidate(candidate)
        for candidate in record.get("meaning_candidates", [])
        if isinstance(candidate, dict) and meaningful_candidate(candidate)
    ]
    if not candidates:
        return None
    return {
        "record_id": record["record_id"],
        "source_kind": record.get("source_kind", "unknown"),
        "lemma": record.get("lemma", ""),
        "normalized_surfaces": sorted({
            normalize_key(value)
            for value in record.get("normalized_surfaces", [])
            if normalize_key(value)
        }),
        "readings": sorted({
            normalize_key(value)
            for value in record.get("readings", [])
            if normalize_key(value)
        }),
        "part_of_speech": list(record.get("part_of_speech") or []),
        "domains": list(record.get("domains") or []),
        "meaning_candidates": candidates,
        "runtime_mode": "candidate-only",
        "automatic_sense_selection_allowed": False,
        "automatic_parameter_application_allowed": False,
        "automatic_external_action_allowed": False,
    }


def _configure_database(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA page_size=4096;
        PRAGMA journal_mode=OFF;
        PRAGMA synchronous=OFF;
        PRAGMA locking_mode=EXCLUSIVE;
        PRAGMA temp_store=MEMORY;
        PRAGMA auto_vacuum=NONE;
        PRAGMA application_id=1146314064;
        PRAGMA user_version=1;
        """
    )


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE records (
            record_id TEXT PRIMARY KEY,
            source_kind TEXT NOT NULL,
            lemma TEXT NOT NULL,
            part_of_speech_json TEXT NOT NULL,
            domains_json TEXT NOT NULL,
            candidates_json TEXT NOT NULL
        ) WITHOUT ROWID;
        CREATE TABLE surfaces (
            surface TEXT NOT NULL,
            record_id TEXT NOT NULL,
            PRIMARY KEY (surface, record_id)
        ) WITHOUT ROWID;
        CREATE TABLE readings (
            reading TEXT NOT NULL,
            record_id TEXT NOT NULL,
            PRIMARY KEY (reading, record_id)
        ) WITHOUT ROWID;
        CREATE TABLE meanings (
            candidate_id TEXT PRIMARY KEY,
            record_id TEXT NOT NULL
        ) WITHOUT ROWID;
        """
    )


def compile_candidates(
    *,
    review_root: Path,
    compiled_root: Path,
    shard_size: int = 10000,
) -> dict[str, Any]:
    del shard_size  # retained only for CLI compatibility with the prior format
    source_path = review_root / "review-records.jsonl"
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    records: list[dict[str, Any]] = []
    excluded = Counter()
    for record in iter_jsonl(source_path):
        selected = candidate_record(record)
        if selected is None:
            blockers = set(record.get("review_blockers") or [])
            reason = next(
                iter(sorted(blockers.intersection(STRUCTURAL_BLOCKERS))),
                "no-usable-meaning-candidate",
            )
            excluded[reason] += 1
            continue
        records.append(selected)
    records.sort(key=lambda item: item["record_id"])

    if compiled_root.exists():
        shutil.rmtree(compiled_root)
    compiled_root.mkdir(parents=True, exist_ok=True)
    database_path = compiled_root / DB_NAME
    connection = sqlite3.connect(database_path)
    try:
        _configure_database(connection)
        _create_schema(connection)
        source_counts = Counter()
        meaning_candidate_count = 0
        surface_rows: list[tuple[str, str]] = []
        reading_rows: list[tuple[str, str]] = []
        meaning_rows: list[tuple[str, str]] = []
        record_rows: list[tuple[str, str, str, str, str, str]] = []

        for record in records:
            record_id = record["record_id"]
            source_counts[record["source_kind"]] += 1
            record_rows.append((
                record_id,
                record["source_kind"],
                record["lemma"],
                json_text(record["part_of_speech"]),
                json_text(record["domains"]),
                json_text(record["meaning_candidates"]),
            ))
            surface_rows.extend(
                (surface, record_id)
                for surface in record["normalized_surfaces"]
            )
            reading_rows.extend(
                (reading, record_id)
                for reading in record["readings"]
            )
            for candidate in record["meaning_candidates"]:
                meaning_rows.append((candidate["candidate_id"], record_id))
                meaning_candidate_count += 1

        connection.executemany(
            "INSERT INTO records VALUES (?, ?, ?, ?, ?, ?)",
            record_rows,
        )
        connection.executemany(
            "INSERT INTO surfaces VALUES (?, ?)",
            sorted(set(surface_rows)),
        )
        connection.executemany(
            "INSERT INTO readings VALUES (?, ?)",
            sorted(set(reading_rows)),
        )
        connection.executemany(
            "INSERT INTO meanings VALUES (?, ?)",
            sorted(set(meaning_rows)),
        )
        connection.commit()
        connection.execute("VACUUM")
        connection.execute("PRAGMA optimize")
        connection.commit()
    finally:
        connection.close()

    database_sha = sha256_file(database_path)
    manifest = {
        "schema_version": "2.0.0",
        "mode": "source-validated-semantic-candidates",
        "storage": "sqlite3-read-only-index",
        "database": {
            "path": DB_NAME,
            "sha256": database_sha,
            "bytes": database_path.stat().st_size,
        },
        "record_count": len(records),
        "meaning_candidate_count": meaning_candidate_count,
        "source_counts": dict(sorted(source_counts.items())),
        "excluded_counts": dict(sorted(excluded.items())),
        "candidate_only": True,
        "approved_semantic_effects": False,
        "automatic_sense_selection": False,
        "automatic_parameter_application": False,
        "automatic_external_action": False,
        "preserve_ambiguity": True,
        "source_review_manifest_sha256": sha256_file(
            review_root / "manifest.json"
        ),
    }
    (compiled_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def directory_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(
        (item for item in root.rglob("*") if item.is_file()),
        key=lambda item: str(item.relative_to(root)),
    ):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-root", type=Path, required=True)
    parser.add_argument("--compiled-root", type=Path, required=True)
    parser.add_argument("--shard-size", type=int, default=10000)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.shard_size < 100:
        raise ValueError("shard-size must be at least 100")
    if args.check:
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first = Path(first_dir)
            second = Path(second_dir)
            left = compile_candidates(
                review_root=args.review_root,
                compiled_root=first,
                shard_size=args.shard_size,
            )
            right = compile_candidates(
                review_root=args.review_root,
                compiled_root=second,
                shard_size=args.shard_size,
            )
            left_digest = directory_digest(first)
            right_digest = directory_digest(second)
            if left_digest != right_digest or left != right:
                raise RuntimeError(
                    "semantic candidate SQLite pack is not byte deterministic"
                )
            result = {
                "status": "CHECKED",
                "digest": left_digest,
                "record_count": left["record_count"],
                "meaning_candidate_count": left["meaning_candidate_count"],
            }
    else:
        result = compile_candidates(
            review_root=args.review_root,
            compiled_root=args.compiled_root,
            shard_size=args.shard_size,
        )
        result["status"] = "WRITTEN"
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
