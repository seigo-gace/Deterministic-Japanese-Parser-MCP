#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from unified_semantic_data.frozen_raw_role_factory import (
    build_frozen_raw_role_factory,
    merge_frozen_raw_role_factory_shards,
    plan_role_factory_shards,
)
from unified_semantic_data.raw_intake import validate_intake_manifest


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
        report = plan_role_factory_shards(manifest, args.shard_count)
        args.output_root.mkdir(parents=True, exist_ok=True)
        (args.output_root / "role-shard-plan.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    elif args.shards_root is not None:
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
