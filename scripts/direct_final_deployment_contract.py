#!/usr/bin/env python3
"""Validate whether the compiled dictionary is deployable as completed runtime.

The checked-in 120k Open Lexicon is a lexical identity snapshot. It is useful
for fallback lookup, but it is not the completed semantic dictionary. The
completed deployment path is the direct-final runtime bundle compiled into the
existing OpenLexiconRuntime and SemanticDataRuntime ABIs.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from deterministic_japanese_parser_mcp.direct_final_contract import evaluate_contract


def main() -> int:
    parser = argparse.ArgumentParser()
    configured_system_root = Path(
        os.getenv("DJPMCP_SYSTEM_DICT_DIR", "dictionaries/system")
    )
    parser.add_argument(
        "--compiled-root",
        type=Path,
        default=configured_system_root / "compiled",
    )
    parser.add_argument("--require-direct-final", action="store_true")
    parser.add_argument("--expected-source-records", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = evaluate_contract(
        compiled_root=args.compiled_root,
        require_direct_final=args.require_direct_final,
        expected_source_records=args.expected_source_records,
    )
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
