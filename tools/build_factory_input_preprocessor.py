#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from unified_semantic_data.factory_input_preprocessor import (
    build_factory_input_preprocessor,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter-input", action="append", type=Path, required=True)
    parser.add_argument("--unresolved-input", action="append", type=Path, required=True)
    parser.add_argument("--supplements", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    report = build_factory_input_preprocessor(
        args.adapter_input,
        args.unresolved_input,
        args.output_root,
        supplements_path=args.supplements,
        require_complete=args.require_complete,
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
