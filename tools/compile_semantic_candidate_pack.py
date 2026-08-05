#!/usr/bin/env python3
"""Compile source-validated, review-pending meanings as candidate-only runtime data.

Candidate-only records may be searched and exposed as MeaningGraph sense
candidates. They cannot select a sense, apply pragmatic parameters, create a
task, or authorize an external action.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import shutil
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


def json_line(value: Any) -> str:
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
        glosses = candidate.get("glosses") or []
        text = " ".join(str(value) for value in glosses).casefold()
    return bool(text.strip()) and not any(marker in text for marker in PLACEHOLDER_MARKERS)


def candidate_record(record: dict[str, Any]) -> dict[str, Any] | None:
    if record.get("review_status") in {"rejected", "hold"}:
        return None
    blockers = set(record.get("review_blockers") or [])
    if blockers.intersection(STRUCTURAL_BLOCKERS):
        return None
    candidates = [
        dict(candidate)
        for candidate in record.get("meaning_candidates", [])
        if isinstance(candidate, dict) and meaningful_candidate(candidate)
    ]
    if not candidates:
        return None
    selected = dict(record)
    selected["meaning_candidates"] = candidates
    selected["semantic_targets"] = ["lexicon"]
    selected["runtime_mode"] = "candidate-only"
    selected["candidate_runtime_eligible"] = True
    selected["runtime_eligible"] = False
    selected["automatic_sense_selection_allowed"] = False
    selected["automatic_parameter_application_allowed"] = False
    selected["automatic_external_action_allowed"] = False
    return selected


def write_gzip(path: Path, payload: bytes) -> dict[str, Any]:
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
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "uncompressed_sha256": hashlib.sha256(payload).hexdigest(),
        "uncompressed_bytes": len(payload),
    }


def compile_candidates(
    *,
    review_root: Path,
    compiled_root: Path,
    shard_size: int,
) -> dict[str, Any]:
    source_path = review_root / "review-records.jsonl"
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    records = []
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

    surface_index: dict[str, set[str]] = defaultdict(set)
    reading_index: dict[str, set[str]] = defaultdict(set)
    lemma_index: dict[str, set[str]] = defaultdict(set)
    pos_index: dict[str, set[str]] = defaultdict(set)
    domain_index: dict[str, set[str]] = defaultdict(set)
    meaning_index: dict[str, set[str]] = defaultdict(set)
    locator: dict[str, dict[str, int]] = {}
    source_counts = Counter()
    meaning_candidate_count = 0

    for number, record in enumerate(records):
        record_id = record["record_id"]
        locator[record_id] = {
            "shard": number // shard_size,
            "line": number % shard_size + 1,
        }
        source_counts[record.get("source_kind", "unknown")] += 1
        lemma_index[normalize_key(record.get("lemma"))].add(record_id)
        for surface in record.get("normalized_surfaces", []):
            surface_index[normalize_key(surface)].add(record_id)
        for reading in record.get("readings", []):
            reading_index[normalize_key(reading)].add(record_id)
        for value in record.get("part_of_speech", []):
            pos_index[str(value)].add(record_id)
        for value in record.get("domains", []):
            domain_index[str(value)].add(record_id)
        for candidate in record.get("meaning_candidates", []):
            meaning_index[candidate["candidate_id"]].add(record_id)
            meaning_candidate_count += 1

    outputs: list[dict[str, Any]] = []
    indexes = {
        "surface-index.json.gz": surface_index,
        "reading-index.json.gz": reading_index,
        "lemma-index.json.gz": lemma_index,
        "pos-index.json.gz": pos_index,
        "domain-index.json.gz": domain_index,
        "meaning-index.json.gz": meaning_index,
        "record-locator.json.gz": locator,
    }
    for filename, mapping in indexes.items():
        serializable = {
            key: sorted(value) if isinstance(value, set) else value
            for key, value in sorted(mapping.items())
        }
        payload = (json_line(serializable) + "\n").encode("utf-8")
        metadata = write_gzip(compiled_root / "indexes" / filename, payload)
        metadata["path"] = f"indexes/{filename}"
        outputs.append(metadata)

    for start in range(0, len(records), shard_size):
        selected = records[start : start + shard_size]
        payload = b"".join(
            (json_line(record) + "\n").encode("utf-8")
            for record in selected
        )
        relative = f"records/records-{start // shard_size:04d}.jsonl.gz"
        metadata = write_gzip(compiled_root / relative, payload)
        metadata["path"] = relative
        metadata["record_count"] = len(selected)
        outputs.append(metadata)

    manifest = {
        "schema_version": "1.0.0",
        "mode": "source-validated-semantic-candidates",
        "record_count": len(records),
        "meaning_candidate_count": meaning_candidate_count,
        "source_counts": dict(sorted(source_counts.items())),
        "excluded_counts": dict(sorted(excluded.items())),
        "record_shard_size": shard_size,
        "record_shards": (
            (len(records) + shard_size - 1) // shard_size if records else 0
        ),
        "candidate_only": True,
        "approved_semantic_effects": False,
        "automatic_sense_selection": False,
        "automatic_parameter_application": False,
        "automatic_external_action": False,
        "preserve_ambiguity": True,
        "source_review_manifest_sha256": sha256_file(
            review_root / "manifest.json"
        ),
        "outputs": outputs,
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
                raise RuntimeError("semantic candidate pack is not byte deterministic")
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
