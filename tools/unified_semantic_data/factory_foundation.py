"""Deterministic data-factory foundation inspired by mature MT/NLP compilers.

This module belongs to the offline Data Supply / factory lane. It does not make
semantic decisions and it does not change ParserEngine runtime behaviour.

The foundation provides four reusable mechanics:
1. raw/canonical/lookup-normalization separation,
2. stable lexical identity sidecars,
3. content-addressed stage fingerprints, and
4. stable hash partitioning for incremental rebuilds.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Iterable, Iterator, Sequence
import unicodedata

FOUNDATION_VERSION = "1.0.0"
DEFAULT_PARTITION_COUNT = 256


def _json_line(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stable_unique(values: Iterable[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def canonical_text(value: Any) -> str:
    """Preserve compatibility distinctions while producing a canonical text view.

    NFC is intentionally used here instead of NFKC. Compatibility folding is a
    lookup concern, not an evidence-preservation concern.
    """
    text = unicodedata.normalize("NFC", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def lookup_projection(value: Any) -> str:
    """Build a search-only projection for tolerant dictionary lookup."""
    text = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", "", text).casefold()


def stable_partition(key: str, partition_count: int = DEFAULT_PARTITION_COUNT) -> int:
    """Assign a record to a stable content-independent partition.

    The partition depends only on the immutable record key and partition count;
    inserting another record cannot move unrelated records between partitions.
    """
    if partition_count < 1:
        raise ValueError("partition_count must be positive")
    digest = hashlib.sha256(str(key).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % partition_count


def lexical_identity(record: dict[str, Any]) -> dict[str, Any]:
    """Project one review record into an audit-friendly lexical identity layer.

    This keeps word identity separate from orthographic/lookup projections and
    deliberately preserves ambiguity: no meaning candidate is selected here.
    """
    record_id = str(record.get("record_id") or "").strip()
    if not record_id:
        raise ValueError("record_id is required")

    lemma = canonical_text(record.get("lemma"))
    readings = _stable_unique(
        canonical_text(value) for value in record.get("readings", [])
    )
    parts = _stable_unique(str(value) for value in record.get("part_of_speech", []))

    surface_values: list[str] = []
    for key in ("surfaces", "normalized_surfaces"):
        values = record.get(key) or []
        if isinstance(values, str):
            values = [values]
        surface_values.extend(str(value) for value in values)
    if lemma:
        surface_values.append(lemma)

    form_rows: list[dict[str, str]] = []
    for form in record.get("forms", []) or []:
        if not isinstance(form, dict):
            continue
        for key in ("surface", "normalized", "lemma"):
            value = canonical_text(form.get(key))
            if value:
                surface_values.append(value)
        row = {
            "surface": canonical_text(form.get("surface")),
            "normalized": canonical_text(form.get("normalized")),
            "lemma": canonical_text(form.get("lemma")),
            "reading": canonical_text(form.get("reading")),
            "part_of_speech": str(form.get("part_of_speech") or "").strip(),
        }
        if any(row.values()):
            form_rows.append(row)

    orthographic_forms = _stable_unique(
        canonical_text(value) for value in surface_values
    )
    lookup_forms = _stable_unique(
        lookup_projection(value) for value in orthographic_forms
    )

    source = record.get("source") or {}
    if not isinstance(source, dict):
        source = {}
    source_identity = {
        "dataset": canonical_text(source.get("dataset")),
        "version": canonical_text(source.get("version")),
        "source_id": canonical_text(source.get("source_id")),
    }

    signature = {
        "lemma": lemma,
        "readings": readings,
        "part_of_speech": parts,
        "source_identity": source_identity,
    }
    lexeme_id = "lex:" + _sha256_bytes(_json_line(signature).encode("utf-8"))[:24]

    return {
        "record_id": record_id,
        "lexeme_id": lexeme_id,
        "lemma": lemma,
        "readings": readings,
        "part_of_speech": parts,
        "orthographic_forms": orthographic_forms,
        "lookup_forms": lookup_forms,
        "forms": sorted(
            form_rows,
            key=lambda row: (
                row["surface"],
                row["normalized"],
                row["lemma"],
                row["reading"],
                row["part_of_speech"],
            ),
        ),
        "source_identity": source_identity,
        "normalization": {
            "canonical": "Unicode NFC + whitespace collapse",
            "lookup": "Unicode NFKC + whitespace removal + casefold",
        },
    }


def _iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"JSONL row must be an object: {path}:{line_number}")
            yield value


def _write_deterministic_gzip(source: Path, target: Path) -> dict[str, Any]:
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as src, target.open("wb") as raw:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw,
            compresslevel=9,
            mtime=0,
        ) as zipped:
            shutil.copyfileobj(src, zipped, length=1024 * 1024)
    return {
        "sha256": _sha256_file(target),
        "bytes": target.stat().st_size,
    }


def build_foundation_assets(
    review_root: Path,
    *,
    partition_count: int = DEFAULT_PARTITION_COUNT,
) -> dict[str, Any]:
    """Build stable lexical-identity partitions from factory review records.

    Existing identical partitions are retained byte-for-byte. Only partitions
    whose content digest changed are replaced, which provides a deterministic
    incremental-build primitive without changing approval or runtime semantics.
    """
    if not 1 <= partition_count <= 4096:
        raise ValueError("partition_count must be between 1 and 4096")
    source_path = review_root / "review-records.jsonl"
    if not source_path.is_file():
        raise FileNotFoundError(source_path)

    root = review_root / "factory-foundation"
    partition_root = root / "lexical-partitions"
    partition_root.mkdir(parents=True, exist_ok=True)

    source_sha256 = _sha256_file(source_path)
    record_count = 0
    lexeme_ids: set[str] = set()
    partition_counts: dict[int, int] = {}

    with tempfile.TemporaryDirectory(prefix="djpmcp-factory-") as tmp_name:
        tmp_root = Path(tmp_name)
        handles: dict[int, Any] = {}
        try:
            for record in _iter_jsonl(source_path):
                row = lexical_identity(record)
                record_count += 1
                lexeme_ids.add(row["lexeme_id"])
                partition = stable_partition(row["record_id"], partition_count)
                partition_counts[partition] = partition_counts.get(partition, 0) + 1
                handle = handles.get(partition)
                if handle is None:
                    path = tmp_root / f"part-{partition:04d}.jsonl"
                    handle = path.open("w", encoding="utf-8", newline="\n")
                    handles[partition] = handle
                handle.write(_json_line(row) + "\n")
        finally:
            for handle in handles.values():
                handle.close()

        partitions: list[dict[str, Any]] = []
        written = 0
        reused = 0
        for partition in sorted(partition_counts):
            plain = tmp_root / f"part-{partition:04d}.jsonl"
            candidate = tmp_root / f"part-{partition:04d}.jsonl.gz"
            meta = _write_deterministic_gzip(plain, candidate)
            target = partition_root / candidate.name
            if target.is_file() and _sha256_file(target) == meta["sha256"]:
                reused += 1
            else:
                shutil.copyfile(candidate, target)
                written += 1
            partitions.append(
                {
                    "partition": partition,
                    "record_count": partition_counts[partition],
                    "path": str(target.relative_to(review_root)),
                    "sha256": meta["sha256"],
                    "bytes": meta["bytes"],
                }
            )

    active_names = {Path(item["path"]).name for item in partitions}
    removed = 0
    for path in sorted(partition_root.glob("part-*.jsonl.gz")):
        if path.name not in active_names:
            path.unlink()
            removed += 1

    stage_material = {
        "foundation_version": FOUNDATION_VERSION,
        "source_sha256": source_sha256,
        "partition_count": partition_count,
        "partitions": [
            [item["partition"], item["sha256"], item["record_count"]]
            for item in partitions
        ],
    }
    manifest = {
        "foundation_version": FOUNDATION_VERSION,
        "source": "review-records.jsonl",
        "source_sha256": source_sha256,
        "record_count": record_count,
        "lexeme_count": len(lexeme_ids),
        "partition_count": partition_count,
        "active_partition_count": len(partitions),
        "partitioner": "sha256(record_id)[0:8] modulo partition_count",
        "written_partitions": written,
        "reused_partitions": reused,
        "removed_partitions": removed,
        "stage_hash": _sha256_bytes(_json_line(stage_material).encode("utf-8")),
        "normalization_contract": {
            "raw": "preserved by source/review record; never overwritten here",
            "canonical": "Unicode NFC + whitespace collapse",
            "lookup": "Unicode NFKC + whitespace removal + casefold",
        },
        "boundaries": {
            "semantic_decision": False,
            "automatic_approval": False,
            "runtime_promotion": False,
            "preserve_ambiguity": True,
        },
        "partitions": partitions,
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


def _iter_fingerprint_files(label: str, path: Path) -> Iterator[tuple[str, Path]]:
    if path.is_file():
        yield label, path
        return
    if path.is_dir():
        for child in sorted((item for item in path.rglob("*") if item.is_file()), key=str):
            yield f"{label}/{child.relative_to(path).as_posix()}", child
        return
    yield f"{label}/<missing>", path


def content_fingerprint(
    inputs: Sequence[tuple[str, Path]],
    *,
    parameters: dict[str, Any] | None = None,
) -> str:
    """Hash source bytes + logical paths + transform parameters.

    Logical labels, rather than absolute filesystem paths, make the fingerprint
    reproducible across developer machines and CI runners.
    """
    digest = hashlib.sha256()
    for label, path in sorted(inputs, key=lambda item: item[0]):
        for logical, file_path in _iter_fingerprint_files(label, path):
            digest.update(logical.encode("utf-8"))
            digest.update(b"\0")
            if file_path.is_file():
                digest.update(_sha256_file(file_path).encode("ascii"))
                digest.update(b"\n")
            else:
                digest.update(b"MISSING\n")
    digest.update(b"PARAMETERS\0")
    digest.update(_json_line(parameters or {}).encode("utf-8"))
    return digest.hexdigest()


def load_factory_state(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else None


def can_reuse_pipeline(
    state_path: Path,
    *,
    input_fingerprint: str,
    review_root: Path,
    compiled_root: Path,
    require_compiled: bool,
) -> bool:
    state = load_factory_state(state_path)
    if not state or state.get("input_fingerprint") != input_fingerprint:
        return False
    required = [
        review_root / "manifest.json",
        review_root / "review-records.jsonl",
        review_root / "approved-records.jsonl",
        review_root / "factory-foundation" / "manifest.json",
    ]
    if require_compiled:
        required.append(compiled_root / "manifest.json")
    return all(path.is_file() for path in required)


def write_factory_state(
    path: Path,
    *,
    input_fingerprint: str,
    foundation_manifest: dict[str, Any],
    compiled: bool,
) -> dict[str, Any]:
    state = {
        "foundation_version": FOUNDATION_VERSION,
        "input_fingerprint": input_fingerprint,
        "foundation_stage_hash": foundation_manifest["stage_hash"],
        "compiled": bool(compiled),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return state
