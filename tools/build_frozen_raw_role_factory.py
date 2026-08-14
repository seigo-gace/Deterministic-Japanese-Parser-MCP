#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from unified_semantic_data.frozen_raw_role_factory import (
    build_frozen_raw_role_factory,
    merge_frozen_raw_role_factory_shards,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--profiles", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--shard-index", type=int)
    parser.add_argument("--shard-count", type=int)
    parser.add_argument("--shards-root", type=Path)
    args = parser.parse_args()
    if args.shards_root is not None:
        if args.bundle is not None or args.profiles is not None:
            parser.error("--shards-root cannot be combined with --bundle/--profiles")
        report = merge_frozen_raw_role_factory_shards(
            args.manifest, args.shards_root, args.output_root
        )
    else:
        if args.bundle is None or args.profiles is None:
            parser.error("--bundle and --profiles are required when building")
        report = build_frozen_raw_role_factory(
            args.bundle,
            args.manifest,
            args.profiles,
            args.output_root,
            shard_index=args.shard_index,
            shard_count=args.shard_count,
            compile_adapter=args.shard_count is None,
        )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
