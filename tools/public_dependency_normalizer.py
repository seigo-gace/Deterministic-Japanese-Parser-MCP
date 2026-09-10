#!/usr/bin/env python3
"""Stream-normalize the NICT Wikipedia dependency database.

The source is large (about 3.5 GB decompressed), so this tool never expands it to
one raw file on disk. It reads the .bz2 body inside the official tar.gz and emits
loss-minimized deterministic gzip shards.

Each normalized row has six tab-separated columns:
  1. dependent phrase (JSON string)
  2. exact relation marker such as <を> or <の:の> (JSON string)
  3. head phrase (JSON string)
  4. observed frequency (integer)
  5. dependent has exact semantic-reference match (0/1)
  6. head has exact semantic-reference match (0/1)

The meaning flags never fabricate meanings. Actual definitions/glosses remain in
the separately source-locked semantic reference JSONL files in the same build
artifact. Unmatched endpoints remain explicit and are counted as unresolved.
"""
from __future__ import annotations

import argparse
import bz2
from collections import Counter
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
import tempfile
import unicodedata
from typing import Any, Iterable, Iterator

BODY_BASENAME = "DEP_WIKIPEDIA_V1.0.bz2"
LINE_RE = re.compile(r"^\s*(.*?)\s+(<[^>\r\n]*>)\s+(.*?)\s+([0-9]+)\s*$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def semantic_key(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def parse_relation_line(line: str) -> tuple[str, str, str, int]:
    match = LINE_RE.match(line.rstrip("\r\n"))
    if match is None:
        raise ValueError("line does not match NICT dependency relation format")
    dependent, marker, head, frequency_raw = match.groups()
    dependent = dependent.strip()
    marker = marker.strip()
    head = head.strip()
    frequency = int(frequency_raw)
    if not marker.startswith("<") or not marker.endswith(">"):
        raise ValueError("relation marker is invalid")
    if frequency < 0:
        raise ValueError("frequency must be non-negative")
    return dependent, marker, head, frequency


def _body_member(archive: tarfile.TarFile) -> tarfile.TarInfo:
    matches = [
        member
        for member in archive.getmembers()
        if member.isfile()
        and PurePosixPath(member.name).name.casefold() == BODY_BASENAME.casefold()
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"dependency body not unique: {[(m.name, m.size) for m in matches]}"
        )
    return matches[0]


def iter_source_lines(archive_path: Path) -> Iterator[tuple[int, str]]:
    with tarfile.open(archive_path, mode="r:gz") as archive:
        member = _body_member(archive)
        compressed = archive.extractfile(member)
        if compressed is None:
            raise RuntimeError("cannot extract NICT dependency body")
        with bz2.BZ2File(compressed, mode="rb") as body:
            for line_number, payload in enumerate(body, 1):
                try:
                    line = payload.decode("utf-8", errors="strict")
                except UnicodeDecodeError as exc:
                    raise RuntimeError(
                        f"source is not strict UTF-8 at line {line_number}: {exc}"
                    ) from exc
                yield line_number, line


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def load_semantic_surface_index(reference_roots: Iterable[Path]) -> tuple[set[str], dict[str, Any]]:
    keys: set[str] = set()
    files: list[dict[str, Any]] = []
    paths: list[Path] = []
    for root in reference_roots:
        if root.is_file() and root.suffix == ".jsonl":
            paths.append(root)
        elif root.is_dir():
            paths.extend(sorted(root.rglob("*.jsonl")))
    for path in sorted(set(paths), key=str):
        rows = 0
        with path.open("r", encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle, 1):
                if not raw.strip():
                    continue
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise RuntimeError(f"semantic reference row is not object: {path}:{line_number}")
                rows += 1
                surfaces = [
                    value.get("surface"),
                    value.get("lemma"),
                    *[v for v in _as_list(value.get("surfaces"))],
                    *[v for v in _as_list(value.get("variants"))],
                ]
                for surface in surfaces:
                    if not isinstance(surface, str):
                        continue
                    key = semantic_key(surface)
                    if key:
                        keys.add(key)
        files.append(
            {
                "path": str(path),
                "rows": rows,
                "sha256": sha256_file(path),
            }
        )
    if not files:
        raise RuntimeError("no semantic reference JSONL files found")
    return keys, {"files": files, "unique_surface_keys": len(keys)}


class ShardWriter:
    def __init__(self, root: Path, shard_size: int) -> None:
        self.root = root
        self.shard_size = shard_size
        self.root.mkdir(parents=True, exist_ok=True)
        self.index = 0
        self.rows_in_shard = 0
        self.total_rows = 0
        self.handle = None
        self.raw_handle = None
        self.path: Path | None = None
        self.shards: list[dict[str, Any]] = []

    def _open(self) -> None:
        self.index += 1
        self.rows_in_shard = 0
        self.path = self.root / f"relations-{self.index:05d}.tsv.gz"
        self.raw_handle = self.path.open("wb")
        gz = gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=self.raw_handle,
            compresslevel=6,
            mtime=0,
        )
        self.handle = io.TextIOWrapper(gz, encoding="utf-8", newline="\n")

    def _close(self) -> None:
        if self.handle is None or self.path is None:
            return
        self.handle.flush()
        self.handle.close()
        self.handle = None
        if self.raw_handle is not None and not self.raw_handle.closed:
            self.raw_handle.close()
        start_record = self.total_rows - self.rows_in_shard + 1
        self.shards.append(
            {
                "path": str(self.path),
                "records": self.rows_in_shard,
                "first_record_ordinal": start_record,
                "last_record_ordinal": self.total_rows,
                "compressed_bytes": self.path.stat().st_size,
                "sha256": sha256_file(self.path),
            }
        )
        self.path = None

    def write(
        self,
        dependent: str,
        marker: str,
        head: str,
        frequency: int,
        dependent_meaning: bool,
        head_meaning: bool,
    ) -> None:
        if self.handle is None:
            self._open()
        if self.rows_in_shard >= self.shard_size:
            self._close()
            self._open()
        assert self.handle is not None
        row = "\t".join(
            [
                json.dumps(dependent, ensure_ascii=False, separators=(",", ":")),
                json.dumps(marker, ensure_ascii=False, separators=(",", ":")),
                json.dumps(head, ensure_ascii=False, separators=(",", ":")),
                str(frequency),
                "1" if dependent_meaning else "0",
                "1" if head_meaning else "0",
            ]
        )
        self.handle.write(row + "\n")
        self.rows_in_shard += 1
        self.total_rows += 1

    def close(self) -> list[dict[str, Any]]:
        self._close()
        return self.shards


def normalize(
    archive_path: Path,
    output_root: Path,
    semantic_reference_roots: list[Path],
    source_sha256: str,
    shard_size: int,
) -> dict[str, Any]:
    actual_source_sha = sha256_file(archive_path)
    if source_sha256 and actual_source_sha.casefold() != source_sha256.casefold():
        raise RuntimeError(
            f"source digest mismatch: expected={source_sha256} actual={actual_source_sha}"
        )
    semantic_keys, semantic_manifest = load_semantic_surface_index(semantic_reference_roots)
    relations_root = output_root / "relations"
    writer = ShardWriter(relations_root, shard_size)
    markers: Counter[str] = Counter()
    malformed: list[dict[str, Any]] = []
    total_frequency = 0
    empty_dependent = 0
    empty_head = 0
    dependent_meaning_matches = 0
    head_meaning_matches = 0
    dependent_nonempty = 0
    head_nonempty = 0
    source_lines = 0

    try:
        for line_number, line in iter_source_lines(archive_path):
            source_lines += 1
            try:
                dependent, marker, head, frequency = parse_relation_line(line)
            except Exception as exc:
                if len(malformed) < 100:
                    malformed.append(
                        {
                            "line_number": line_number,
                            "error": str(exc),
                            "line": line.rstrip("\r\n")[:2000],
                        }
                    )
                continue
            markers[marker] += 1
            total_frequency += frequency
            if dependent:
                dependent_nonempty += 1
                dependent_meaning = semantic_key(dependent) in semantic_keys
                if dependent_meaning:
                    dependent_meaning_matches += 1
            else:
                empty_dependent += 1
                dependent_meaning = False
            if head:
                head_nonempty += 1
                head_meaning = semantic_key(head) in semantic_keys
                if head_meaning:
                    head_meaning_matches += 1
            else:
                empty_head += 1
                head_meaning = False
            writer.write(
                dependent,
                marker,
                head,
                frequency,
                dependent_meaning,
                head_meaning,
            )
    finally:
        shards = writer.close()

    if malformed:
        raise RuntimeError(
            f"NICT dependency normalization found malformed source rows: "
            f"count_at_least={len(malformed)} sample={malformed[:10]}"
        )
    if writer.total_rows != source_lines:
        raise RuntimeError(
            f"source row preservation failed: source_lines={source_lines} "
            f"normalized_records={writer.total_rows}"
        )

    manifest = {
        "schema_version": "1.0.0",
        "source_id": "nict-wikipedia-dependency-v1.0",
        "source_sha256": actual_source_sha,
        "source_lines": source_lines,
        "normalized_records": writer.total_rows,
        "malformed_records": 0,
        "total_observed_frequency": total_frequency,
        "record_order": "source_line_order",
        "row_schema": [
            "dependent_json_string",
            "relation_marker_json_string",
            "head_json_string",
            "frequency_integer",
            "dependent_meaning_exact_match_0_or_1",
            "head_meaning_exact_match_0_or_1",
        ],
        "relation_marker_counts": dict(sorted(markers.items())),
        "empty_dependent_records": empty_dependent,
        "empty_head_records": empty_head,
        "semantic_join": {
            "join_key": "NFKC_casefold_surface",
            "meaning_source_policy": "exact match against source-locked semantic reference JSONL only; no generated meanings",
            "reference": semantic_manifest,
            "dependent_nonempty_occurrences": dependent_nonempty,
            "dependent_meaning_match_occurrences": dependent_meaning_matches,
            "dependent_unresolved_occurrences": dependent_nonempty - dependent_meaning_matches,
            "head_nonempty_occurrences": head_nonempty,
            "head_meaning_match_occurrences": head_meaning_matches,
            "head_unresolved_occurrences": head_nonempty - head_meaning_matches,
        },
        "shards": shards,
        "raw_source_committed": False,
        "llm_api_used": False,
        "web_scraping_used": False,
    }
    manifest_path = output_root / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest["manifest_sha256"] = sha256_file(manifest_path)
    return manifest


def self_test() -> dict[str, Any]:
    cases = [
        ("関サバ <を> 食べる 20", ("関サバ", "<を>", "食べる", 20)),
        ("地方 自治 <の:の> 第 ６７号 1", ("地方 自治", "<の:の>", "第 ６７号", 1)),
        ("\u3000 <って:か> まっきー 1", ("", "<って:か>", "まっきー", 1)),
        ("A B C <> D E F 99", ("A B C", "<>", "D E F", 99)),
    ]
    for raw, expected in cases:
        actual = parse_relation_line(raw)
        if actual != expected:
            raise RuntimeError(f"parse self-test failed: {raw!r} {actual!r} != {expected!r}")
    return {"status": "PASS", "cases": len(cases)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--semantic-reference-root", type=Path, action="append", default=[])
    parser.add_argument("--source-sha256", default="")
    parser.add_argument("--shard-size", type=int, default=1_000_000)
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test(), ensure_ascii=False, sort_keys=True))
        return 0
    if args.archive is None or args.output_root is None or not args.semantic_reference_root:
        parser.error("--archive, --output-root and --semantic-reference-root are required")
    if args.shard_size < 10_000:
        parser.error("--shard-size must be at least 10000")
    result = normalize(
        args.archive,
        args.output_root,
        args.semantic_reference_root,
        args.source_sha256,
        args.shard_size,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
