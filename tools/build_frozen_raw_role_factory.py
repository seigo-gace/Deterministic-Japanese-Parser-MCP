#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from unified_semantic_data.frozen_raw_role_factory import build_frozen_raw_role_factory


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--profiles", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    report = build_frozen_raw_role_factory(
        args.bundle, args.manifest, args.profiles, args.output_root
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
