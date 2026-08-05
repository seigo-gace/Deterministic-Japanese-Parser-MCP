"""Review asset and approved runtime compilation for unified semantic data."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable, Iterator

import yaml

from .common import (
    COMPILER_VERSION, SCHEMA_VERSION, MorphologyAnalyzer, _as_list,
    _iter_jsonl, _iter_yaml_or_json, _json_line, _sha256_bytes,
    _sha256_file, _build_record, normalize_key,
)


def iter_source_records(
    open_lexicon_root: Path,
    context_root: Path,
    pack_roots: Iterable[Path],
    analyzer: MorphologyAnalyzer,
) -> Iterator[dict[str, Any]]:
    if open_lexicon_root.exists():
        paths = sorted(
            [
                *open_lexicon_root.rglob("*.jsonl"),
                *open_lexicon_root.rglob("*.jsonl.gz"),
            ],
            key=str,
        )
        for path in paths:
            for raw in _iter_jsonl(path):
                yield _build_record(
                    raw,
                    source_kind="open_lexicon",
                    analyzer=analyzer,
                )
    if context_root.exists():
        paths = sorted(
            [*context_root.rglob("*.yaml"), *context_root.rglob("*.yml")],
            key=str,
        )
        for path in paths:
            if path.name == "index.yaml":
                continue
            for raw in _iter_yaml_or_json(path):
                yield _build_record(
                    raw,
                    source_kind="context",
                    analyzer=analyzer,
                )
    for pack_root in pack_roots:
        if not pack_root.exists():
            continue
        source_kind = "user_pack" if "user" in pack_root.name else "domain_pack"
        paths = sorted(
            [
                *pack_root.rglob("*.yaml"),
                *pack_root.rglob("*.yml"),
                *pack_root.rglob("*.json"),
                *pack_root.rglob("*.jsonl"),
                *pack_root.rglob("*.jsonl.gz"),
            ],
            key=str,
        )
        for path in paths:
            iterator = (
                _iter_jsonl(path)
                if ".jsonl" in path.name
                else _iter_yaml_or_json(path)
            )
            for raw in iterator:
                yield _build_record(
                    raw,
                    source_kind=source_kind,
                    analyzer=analyzer,
                )


def _extract_baseline_surfaces(system_root: Path) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    metaphor_root = system_root / "metaphors"
    paths = sorted(metaphor_root.glob("*.json")) if metaphor_root.exists() else []
    for path in paths:
        if path.name in {"manifest.json", "overrides.json"}:
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        for item in doc.get("entries", []):
            expression = normalize_key(item.get("expression"))
            if expression:
                result[expression].add("metaphor")

    synonym_paths = [system_root / "synonyms.yaml"]
    synonym_dir = system_root / "synonyms.d"
    if synonym_dir.exists():
        synonym_paths.extend(sorted(synonym_dir.glob("*.yaml")))
    for path in synonym_paths:
        if not path.exists():
            continue
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for canonical, values in doc.get("groups", {}).items():
            for value in [canonical, *_as_list(values)]:
                key = normalize_key(value)
                if key:
                    result[key].add("synonym")

    feature_root = system_root / "language_features.d"
    paths = sorted(feature_root.glob("*.yaml")) if feature_root.exists() else []
    for path in paths:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for item in doc.get("entries", []):
            for value in _as_list(item.get("surfaces")):
                key = normalize_key(value)
                if key:
                    result[key].add("language_feature")
    return result


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


def build_review_assets(
    *,
    open_lexicon_root: Path,
    context_root: Path,
    pack_roots: list[Path],
    output_root: Path,
    system_root: Path,
) -> dict[str, Any]:
    analyzer = MorphologyAnalyzer()
    records = list(
        iter_source_records(
            open_lexicon_root,
            context_root,
            pack_roots,
            analyzer,
        )
    )
    records.sort(key=lambda item: (item["source_kind"], item["record_id"]))

    ids: set[str] = set()
    duplicate_ids: list[str] = []
    surface_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    baseline = _extract_baseline_surfaces(system_root)
    link_rows: list[dict[str, Any]] = []
    for record in records:
        if record["record_id"] in ids:
            duplicate_ids.append(record["record_id"])
        ids.add(record["record_id"])
        linked = sorted(
            {
                target
                for surface in record["normalized_surfaces"]
                for target in baseline.get(surface, set())
            }
        )
        if linked:
            link_rows.append(
                {
                    "record_id": record["record_id"],
                    "existing_targets": linked,
                }
            )
        record["existing_runtime_links"] = linked
        for surface in record["normalized_surfaces"]:
            surface_map[surface].append(record)

    collisions: list[dict[str, Any]] = []
    for surface, items in sorted(surface_map.items()):
        if len(items) < 2:
            continue
        signatures = {
            (
                tuple(item["part_of_speech"]),
                tuple(item["domains"]),
                tuple(
                    candidate["candidate_id"]
                    for candidate in item["meaning_candidates"]
                ),
            )
            for item in items
        }
        collisions.append(
            {
                "normalized_surface": surface,
                "record_ids": sorted(item["record_id"] for item in items),
                "collision_type": (
                    "same-surface-different-analysis"
                    if len(signatures) > 1
                    else "duplicate-surface"
                ),
                "runtime_resolution": "preserve-all-candidates",
            }
        )
    if duplicate_ids:
        raise ValueError(
            f"duplicate record ids: {sorted(set(duplicate_ids))[:20]}"
        )

    output_root.mkdir(parents=True, exist_ok=True)
    review_text = "".join(_json_line(item) + "\n" for item in records)
    queue = [
        item
        for item in records
        if item["review_blockers"] or item["review_status"] != "approved"
    ]
    queue_text = "".join(_json_line(item) + "\n" for item in queue)
    eligible = [item for item in records if item["runtime_eligible"]]
    eligible_text = "".join(_json_line(item) + "\n" for item in eligible)
    collision_text = "".join(_json_line(item) + "\n" for item in collisions)
    links_text = "".join(_json_line(item) + "\n" for item in link_rows)
    files = {
        "review-records.jsonl": review_text,
        "review-queue.jsonl": queue_text,
        "runtime-candidates.jsonl": eligible_text,
        "collision-report.jsonl": collision_text,
        "existing-runtime-links.jsonl": links_text,
    }
    for name, text in files.items():
        (output_root / name).write_text(
            text,
            encoding="utf-8",
            newline="\n",
        )

    source_counts = Counter(item["source_kind"] for item in records)
    blocker_counts = Counter(
        blocker for item in records for blocker in item["review_blockers"]
    )
    target_counts = Counter(
        target for item in records for target in item["semantic_targets"]
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "compiler_version": COMPILER_VERSION,
        "morphology_backend": analyzer.backend,
        "total_records": len(records),
        "source_counts": dict(sorted(source_counts.items())),
        "runtime_eligible_records": len(eligible),
        "review_queue_records": len(queue),
        "collision_surfaces": len(collisions),
        "existing_runtime_link_records": len(link_rows),
        "review_blocker_counts": dict(sorted(blocker_counts.items())),
        "semantic_target_counts": dict(sorted(target_counts.items())),
        "boundaries": {
            "automatic_definition_generation": False,
            "automatic_approval": False,
            "automatic_runtime_promotion": False,
            "preserve_ambiguity": True,
            "approved_only_compile": True,
        },
        "files": {
            name: {
                "sha256": _sha256_bytes(text.encode("utf-8")),
                "bytes": len(text.encode("utf-8")),
            }
            for name, text in files.items()
        },
    }
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def compile_approved(
    review_root: Path,
    compiled_root: Path,
    *,
    shard_size: int = 10000,
) -> dict[str, Any]:
    source_path = review_root / "runtime-candidates.jsonl"
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    records = list(_iter_jsonl(source_path))
    for record in records:
        record.pop("_source_path", None)
        record.pop("_source_line", None)
        if (
            record.get("review_status") != "approved"
            or record.get("review_blockers")
            or record.get("runtime_eligible") is not True
        ):
            raise ValueError(
                f"unapproved record reached compiler: {record.get('record_id')}"
            )
    records.sort(key=lambda item: item["record_id"])

    surface_index: dict[str, set[str]] = defaultdict(set)
    reading_index: dict[str, set[str]] = defaultdict(set)
    lemma_index: dict[str, set[str]] = defaultdict(set)
    pos_index: dict[str, set[str]] = defaultdict(set)
    domain_index: dict[str, set[str]] = defaultdict(set)
    meaning_index: dict[str, set[str]] = defaultdict(set)
    target_index: dict[str, set[str]] = defaultdict(set)
    locator: dict[str, dict[str, int]] = {}
    for number, record in enumerate(records):
        locator[record["record_id"]] = {
            "shard": number // shard_size,
            "line": number % shard_size + 1,
        }
        lemma_index[normalize_key(record["lemma"])].add(record["record_id"])
        for value in record["normalized_surfaces"]:
            surface_index[value].add(record["record_id"])
        for value in record["readings"]:
            reading_index[normalize_key(value)].add(record["record_id"])
        for value in record["part_of_speech"]:
            pos_index[value].add(record["record_id"])
        for value in record["domains"]:
            domain_index[value].add(record["record_id"])
        for item in record["meaning_candidates"]:
            meaning_index[item["candidate_id"]].add(record["record_id"])
        for value in record["semantic_targets"]:
            target_index[value].add(record["record_id"])

    if compiled_root.exists():
        shutil.rmtree(compiled_root)
    compiled_root.mkdir(parents=True, exist_ok=True)
    outputs: list[dict[str, Any]] = []
    indexes = {
        "surface-index.json.gz": surface_index,
        "reading-index.json.gz": reading_index,
        "lemma-index.json.gz": lemma_index,
        "pos-index.json.gz": pos_index,
        "domain-index.json.gz": domain_index,
        "meaning-index.json.gz": meaning_index,
        "semantic-target-index.json.gz": target_index,
        "record-locator.json.gz": locator,
    }
    for filename, mapping in indexes.items():
        serializable = {
            key: sorted(value) if isinstance(value, set) else value
            for key, value in sorted(mapping.items())
        }
        payload = (_json_line(serializable) + "\n").encode("utf-8")
        metadata = _write_gzip(
            compiled_root / "indexes" / filename,
            payload,
        )
        metadata["path"] = f"indexes/{filename}"
        outputs.append(metadata)

    for start in range(0, len(records), shard_size):
        selected = records[start : start + shard_size]
        payload = b"".join(
            (_json_line(item) + "\n").encode("utf-8") for item in selected
        )
        relative = f"records/records-{start // shard_size:04d}.jsonl.gz"
        metadata = _write_gzip(compiled_root / relative, payload)
        metadata["path"] = relative
        metadata["record_count"] = len(selected)
        outputs.append(metadata)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "compiler_version": COMPILER_VERSION,
        "mode": "approved-unified-semantic-data",
        "record_count": len(records),
        "record_shard_size": shard_size,
        "record_shards": (
            (len(records) + shard_size - 1) // shard_size if records else 0
        ),
        "approved_only": True,
        "preserve_ambiguity": True,
        "automatic_external_action": False,
        "source_review_manifest_sha256": _sha256_file(
            review_root / "manifest.json"
        ),
        "outputs": outputs,
    }
    (compiled_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _directory_digest(root: Path) -> str:
    digest = hashlib.sha256()
    paths = sorted(
        (item for item in root.rglob("*") if item.is_file()),
        key=lambda item: str(item.relative_to(root)),
    )
    for path in paths:
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def check_determinism(args: argparse.Namespace) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
        first = Path(first_dir)
        second = Path(second_dir)
        build_review_assets(
            open_lexicon_root=args.open_lexicon_root,
            context_root=args.context_root,
            pack_roots=args.pack_root,
            output_root=first / "review",
            system_root=args.system_root,
        )
        build_review_assets(
            open_lexicon_root=args.open_lexicon_root,
            context_root=args.context_root,
            pack_roots=args.pack_root,
            output_root=second / "review",
            system_root=args.system_root,
        )
        compile_approved(
            first / "review",
            first / "compiled",
            shard_size=args.shard_size,
        )
        compile_approved(
            second / "review",
            second / "compiled",
            shard_size=args.shard_size,
        )
        first_digest = _directory_digest(first)
        second_digest = _directory_digest(second)
        if first_digest != second_digest:
            raise RuntimeError(
                "unified semantic data pipeline is not byte deterministic"
            )
        return {"status": "CHECKED", "digest": first_digest}
