#!/usr/bin/env python3
"""Create deterministic, review-only dictionary proposals from unresolved logs."""
import argparse
import json
import re
from pathlib import Path
import yaml

SUFFIXES = {
    "するな": "prohibition", "しないで": "prohibition", "禁止": "prohibition",
    "残せ": "preserve", "維持しろ": "preserve", "壊すな": "preserve",
    "変更しろ": "modify", "修正しろ": "modify", "更新しろ": "modify",
    "削除しろ": "remove", "消せ": "remove", "外せ": "remove",
    "比較しろ": "comparison", "比べろ": "comparison",
    "決定しろ": "decision", "採用しろ": "decision",
    "検証しろ": "verification_criteria", "確認しろ": "verification_criteria",
    "公開しろ": "action", "反映しろ": "action", "実行しろ": "request",
}
COMMAND_ENDINGS = re.compile(
    r"(?:を|に|で|は)?(?:全部|すべて)?(?:ほげろ|片付けろ|やれ|しろ|してくれ|してください|するな|しないで|比較しろ|検証しろ|公開しろ)[。！？]?$"
)
PARTICLE_SPLIT = re.compile(r"(?:を|に|で|へ|が|は|と|から|まで)")


def metaphor_candidates(text: str) -> list[dict]:
    cleaned = COMMAND_ENDINGS.sub("", text.strip())
    chunks = [x.strip(" 、。！？『』「」") for x in PARTICLE_SPLIT.split(cleaned)]
    candidates = []
    for chunk in chunks:
        if 2 <= len(chunk) <= 24 and not chunk.isdigit():
            candidates.append({
                "expression": chunk,
                "interpretation": "",
                "context": [text],
                "domain": "unclassified",
                "reason": "unresolved phrase extracted from parser log",
                "requires_review": True,
            })
    return candidates[:5]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True)
    parser.add_argument("--out", default="proposals/from_logs.yaml")
    args = parser.parse_args()

    rows = []
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
        proposals = []
        for suffix, intent in SUFFIXES.items():
            if suffix in text:
                proposals.append({
                    "intent": intent,
                    "pattern": re.escape(text),
                    "source_text": text,
                    "reason": f"detected command marker: {suffix}",
                    "requires_review": True,
                })
        rows.append({
            "original_text": text,
            "rule_proposals": proposals,
            "metaphor_candidates": metaphor_candidates(text),
            "requires_review": True,
        })

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump({"version": "1.0.0", "proposals": rows}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"wrote {len(rows)} review items to {out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
