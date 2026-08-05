#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from unified_semantic_data.pipeline import (
    build_review_assets,
    check_determinism,
    compile_approved,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OPEN_LEXICON_ROOT = ROOT / "dictionaries/system/lexicon.d"
DEFAULT_CONTEXT_ROOT = ROOT / "research/context_collection/expansion_v3"
DEFAULT_PACK_ROOTS = (
    ROOT / "dictionaries/domain_packs",
    ROOT / "dictionaries/user_packs",
)
DEFAULT_OUTPUT_ROOT = ROOT / "reports/unified-semantic-data"
DEFAULT_COMPILED_ROOT = ROOT / "dictionaries/system/compiled/semantic_data"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--open-lexicon-root",
        type=Path,
        default=DEFAULT_OPEN_LEXICON_ROOT,
    )
    parser.add_argument(
        "--context-root",
        type=Path,
        default=DEFAULT_CONTEXT_ROOT,
    )
    parser.add_argument("--pack-root", type=Path, action="append", default=[])
    parser.add_argument(
        "--system-root",
        type=Path,
        default=ROOT / "dictionaries/system",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
    )
    parser.add_argument(
        "--compiled-root",
        type=Path,
        default=DEFAULT_COMPILED_ROOT,
    )
    parser.add_argument("--shard-size", type=int, default=10000)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--compile-approved", action="store_true")
    args = parser.parse_args()
    if not args.pack_root:
        args.pack_root = list(DEFAULT_PACK_ROOTS)
    if args.shard_size < 100:
        raise ValueError("shard-size must be at least 100")

    if args.check:
        result = check_determinism(args)
    else:
        review = build_review_assets(
            open_lexicon_root=args.open_lexicon_root,
            context_root=args.context_root,
            pack_roots=args.pack_root,
            output_root=args.output_root,
            system_root=args.system_root,
        )
        result = {"status": "WRITTEN", "review": review}
        if args.compile_approved:
            result["compiled"] = compile_approved(
                args.output_root,
                args.compiled_root,
                shard_size=args.shard_size,
            )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
