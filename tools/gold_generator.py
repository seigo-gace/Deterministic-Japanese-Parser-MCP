#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True)
    parser.add_argument("--out", default="proposals/gold_candidates.json")
    args = parser.parse_args()

    cases = []
    seen = set()
    for line in Path(args.log).read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("overall_status") not in {"PARTIAL", "FAILED"}:
            continue
        text = row.get("original_text", "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cases.append({
            "id": f"CAND-{len(cases) + 1:04d}",
            "text": text,
            "expected": {"intents": [], "metaphors": []},
            "requires_review": True,
        })

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"version": "1.0.0", "cases": cases}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"wrote {len(cases)} unique candidates to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
