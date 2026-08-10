#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from unified_semantic_data.semantic_labeler import build_semantic_enrichment_queue


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build deterministic semantic meaning-enrichment review queue."
    )
    parser.add_argument("--review-records", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--reference-root", type=Path, action="append", default=[])
    args = parser.parse_args()
    report = build_semantic_enrichment_queue(
        args.review_records,
        args.output_root,
        reference_roots=args.reference_root,
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
