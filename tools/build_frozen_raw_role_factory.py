#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
from typing import Any, Iterator

from unified_semantic_data import frozen_raw_role_factory as role_factory
from unified_semantic_data.raw_intake import validate_intake_manifest


_NICT_DEPENDENCY_SOURCE_ID = "nict-wikipedia-dependency-v1.0"
_NICT_NORMALIZED_COLUMN_COUNT = 6
_TATOEBA_TRANSCRIPTION_SOURCE_ID = "tatoeba-jpn-transcriptions"
_TATOEBA_TRANSCRIPTION_COLUMN_COUNT = 5
_BASE_ITER_RECORDS = role_factory._iter_records


def _iter_nict_dependency_records(
    path: Path, profile: dict[str, Any]
) -> Iterator[dict[str, Any]]:
    """Read the already-normalized NICT six-column relation format losslessly."""
    encodings = list(profile.get("encodings") or ["utf-8"])
    if encodings != ["utf-8"]:
        raise ValueError(
            f"NICT dependency normalized input must be strict UTF-8: {encodings}"
        )
    delimiter = str(profile.get("delimiter") or "")
    if delimiter != "\t":
        raise ValueError(
            f"NICT dependency normalized input must use literal tab delimiter: {delimiter!r}"
        )

    with role_factory._open_decompressed(path) as raw, io.TextIOWrapper(
        raw, encoding="utf-8", errors="strict", newline=""
    ) as text:
        for line_number, line in enumerate(text, 1):
            payload = line.rstrip("\r\n")
            if not payload:
                continue
            columns = payload.split("\t")
            if len(columns) != _NICT_NORMALIZED_COLUMN_COUNT:
                raise ValueError(
                    f"NICT_DEPENDENCY_COLUMN_COUNT:{path}:{line_number}:{len(columns)}"
                )
            try:
                dependent = json.loads(columns[0])
                marker = json.loads(columns[1])
                head = json.loads(columns[2])
                frequency = int(columns[3])
                dependent_meaning = int(columns[4])
                head_meaning = int(columns[5])
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"NICT_DEPENDENCY_ROW_INVALID:{path}:{line_number}:{exc}"
                ) from exc
            if not all(isinstance(value, str) for value in (dependent, marker, head)):
                raise ValueError(
                    f"NICT_DEPENDENCY_TEXT_FIELD_INVALID:{path}:{line_number}"
                )
            if frequency < 0 or dependent_meaning not in {0, 1} or head_meaning not in {0, 1}:
                raise ValueError(
                    f"NICT_DEPENDENCY_NUMERIC_FIELD_INVALID:{path}:{line_number}"
                )
            yield {
                "surfaces": [value for value in (dependent, head) if value],
                "dependent": dependent,
                "relation_marker": marker,
                "head": head,
                "frequency": frequency,
                "dependent_meaning_exact_match": bool(dependent_meaning),
                "head_meaning_exact_match": bool(head_meaning),
                "normalized_source_format": _NICT_DEPENDENCY_SOURCE_ID,
            }


def _iter_tatoeba_transcription_records(
    path: Path, profile: dict[str, Any]
) -> Iterator[dict[str, Any]]:
    """Read Tatoeba transcription TSV with quotes preserved as ordinary text."""
    encodings = list(profile.get("encodings") or ["utf-8"])
    if encodings != ["utf-8"]:
        raise ValueError(
            f"Tatoeba transcription input must be strict UTF-8: {encodings}"
        )
    delimiter = str(profile.get("delimiter") or "")
    if delimiter != "\t":
        raise ValueError(
            f"Tatoeba transcription input must use literal tab delimiter: {delimiter!r}"
        )

    with role_factory._open_decompressed(path) as raw, io.TextIOWrapper(
        raw, encoding="utf-8", errors="strict", newline=""
    ) as text:
        pending_columns: list[str] | None = None
        pending_line_number = 0
        for line_number, line in enumerate(text, 1):
            payload = line.rstrip("\r\n")
            if not payload:
                continue
            columns = payload.split("\t")
            if len(columns) == _TATOEBA_TRANSCRIPTION_COLUMN_COUNT:
                if pending_columns is not None:
                    yield {"columns": pending_columns}
                pending_columns = columns
                pending_line_number = line_number
                continue
            if len(columns) == 1 and pending_columns is not None:
                pending_columns[-1] += columns[0]
                continue
            raise ValueError(
                "TATOEBA_TRANSCRIPTION_COLUMN_COUNT:"
                f"{path}:{line_number}:{len(columns)}:pending={pending_line_number}"
            )
        if pending_columns is not None:
            yield {"columns": pending_columns}


def _iter_factory_ready_records(
    path: Path, profile: dict[str, Any]
) -> Iterator[dict[str, Any]]:
    source_id = str(profile.get("source_id") or "")
    if source_id == _NICT_DEPENDENCY_SOURCE_ID:
        yield from _iter_nict_dependency_records(path, profile)
        return
    if source_id == _TATOEBA_TRANSCRIPTION_SOURCE_ID:
        yield from _iter_tatoeba_transcription_records(path, profile)
        return
    yield from _BASE_ITER_RECORDS(path, profile)


def _install_factory_ready_parsers() -> None:
    role_factory._iter_records = _iter_factory_ready_records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--profiles", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--shard-index", type=int)
    parser.add_argument("--shard-count", type=int)
    parser.add_argument("--shards-root", type=Path)
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    if args.plan_only:
        if args.bundle is not None or args.profiles is not None or args.shards_root is not None:
            parser.error("--plan-only cannot be combined with --bundle/--profiles/--shards-root")
        if args.shard_count is None or args.shard_index is not None:
            parser.error("--plan-only requires --shard-count and forbids --shard-index")
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        validate_intake_manifest(manifest)
        report = role_factory.plan_role_factory_shards(manifest, args.shard_count)
        args.output_root.mkdir(parents=True, exist_ok=True)
        (args.output_root / "role-shard-plan.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    elif args.shards_root is not None:
        if args.bundle is not None or args.profiles is not None:
            parser.error("--shards-root cannot be combined with --bundle/--profiles")
        report = role_factory.merge_frozen_raw_role_factory_shards(
            args.manifest, args.shards_root, args.output_root
        )
    else:
        if args.bundle is None or args.profiles is None:
            parser.error("--bundle and --profiles are required when building")
        _install_factory_ready_parsers()
        report = role_factory.build_frozen_raw_role_factory(
            args.bundle,
            args.manifest,
            args.profiles,
            args.output_root,
            shard_index=args.shard_index,
            shard_count=args.shard_count,
            compile_adapter=args.shard_count is None,
        )
    printable = report
    if args.plan_only:
        printable = {
            key: report[key]
            for key in (
                "algorithm",
                "shard_count",
                "declared_payload_count",
                "declared_payload_bytes",
                "plan_sha256",
            )
        }
        printable["shard_declared_payload_bytes"] = [
            row["declared_payload_bytes"] for row in report["shards"]
        ]
    print(json.dumps(printable, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
