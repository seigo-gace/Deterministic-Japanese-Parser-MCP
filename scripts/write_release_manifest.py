#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys


def file_record(path: Path, root: Path) -> dict[str, str | int]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--include", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    root = args.root.resolve()
    files: list[Path] = []
    for value in args.include:
        target = (root / value).resolve() if not value.is_absolute() else value.resolve()
        if not target.exists():
            parser.error(f"manifest input does not exist: {target}")
        if target.is_file():
            files.append(target)
        else:
            files.extend(path for path in target.rglob("*") if path.is_file())

    records = [file_record(path, root) for path in sorted(set(files))]
    if not records:
        parser.error("manifest contains no files")

    manifest = {
        "schema": "djpmcp-release-manifest-v1",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "file_count": len(records),
        "total_bytes": sum(int(item["bytes"]) for item in records),
        "files": records,
    }
    output = args.output if args.output.is_absolute() else root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
