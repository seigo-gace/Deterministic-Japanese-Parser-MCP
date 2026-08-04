#!/usr/bin/env python3
"""Rehydrate the validated 5,000-candidate inventory and emit one YAML per entry."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import lzma
import shutil
import unicodedata
from collections import Counter
from pathlib import Path

EXPECTED_XZ_SHA256 = "2945cfb324df112001af3d1d72d8e529ba6ddb351419f9185b6e8f732f661db1"
EXPECTED_COUNTS = {
    "slang": 1000,
    "onomatopoeia": 700,
    "modality": 500,
    "honorific": 500,
    "discourse": 400,
    "metaphor": 500,
    "dialect": 400,
    "media_community": 500,
    "reference": 300,
    "epistemic": 200,
}
FEATURE_TYPE = {
    "media_community": "slang",
    **{key: key for key in EXPECTED_COUNTS if key != "media_community"},
}
DOMAIN = {
    "slang": "sns", "onomatopoeia": "casual", "modality": "formal",
    "honorific": "formal", "discourse": "casual", "metaphor": "business",
    "dialect": "casual", "media_community": "fandom", "reference": "formal",
    "epistemic": "formal",
}
COMMUNITY = {
    "slang": "若者", "onomatopoeia": "一般", "modality": "一般",
    "honorific": "一般", "discourse": "一般", "metaphor": "ビジネス",
    "dialect": "地域", "media_community": "ネット", "reference": "一般",
    "epistemic": "一般",
}

def q(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)

def normalized(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()

def load_inventory(data_dir: Path) -> list[list[object]]:
    parts = sorted(data_dir.glob("context-v3-surface-inventory.json.xz.part*.b64"))
    if len(parts) != 9:
        raise SystemExit(f"expected 9 inventory parts, found {len(parts)}")
    encoded = "".join(part.read_text(encoding="ascii").strip() for part in parts)
    compressed = base64.b64decode(encoded, validate=True)
    digest = hashlib.sha256(compressed).hexdigest()
    if digest != EXPECTED_XZ_SHA256:
        raise SystemExit(f"inventory SHA-256 mismatch: {digest}")
    rows = json.loads(lzma.decompress(compressed).decode("utf-8"))
    if len(rows) != 5000:
        raise SystemExit(f"expected 5000 entries, found {len(rows)}")
    counts = Counter(row[1] for row in rows)
    if dict(counts) != EXPECTED_COUNTS:
        raise SystemExit(f"category quota mismatch: {dict(counts)}")
    surfaces = [normalized(str(row[2])) for row in rows]
    if len(set(surfaces)) != 5000:
        raise SystemExit("normalized surfaces are not globally unique")
    return rows

def yaml_text(row: list[object]) -> str:
    entry_id, category, surface, reading, variants, sources = row
    category = str(category)
    surface = str(surface)
    variants = [str(v) for v in (variants or [])]
    sources = [str(s) for s in (sources or [])]
    risk = category in {"modality", "reference", "epistemic"}
    politeness = "formal" if category in {"modality", "honorific", "epistemic"} else "casual"
    positive = f"{surface} を候補表現として検出する。"
    negative = f"引用・否定・疑問内の {surface} を確定意味として扱わない。"
    boundary = f"文脈不足時の {surface} は needs-evidence のまま保持する。"
    lines = [
        f"entry_id: {q(str(entry_id))}",
        f"surface: {q(surface)}",
    ]
    if reading:
        lines.append(f"reading: {q(str(reading))}")
    if variants:
        lines.append("variants:")
        lines.extend(f"  - {q(v)}" for v in variants)
    lines.extend([
        f"feature_type: {q(FEATURE_TYPE[category])}",
        "meaning_candidates:",
        "  - polarity: contextual",
        "    intensity: 0.0",
        "    target_type: state",
        f"    context: {q('意味・極性・使用域のEvidence review前')}",
        "    examples:",
        f"      - {q(positive)}",
        f"      - {q(boundary)}",
        f"    meaning: {q('収集段階のSurface Candidate。意味は未確定。')}",
        f"domain: {q(DOMAIN[category])}",
        f"politeness: {q(politeness)}",
        'generation: "all"',
        f"community: {q(COMMUNITY[category])}",
        "source:",
    ])
    lines.extend(f"  - {q(s)}" for s in sources)
    lines.extend([
        'source_version: "2026-08"',
        'license: "確認中"',
        'review_status: "needs-evidence"',
        f"external_action_risk: {'true' if risk else 'false'}",
        "positive_examples:",
        f"  - {q(positive)}",
        "negative_examples:",
        f"  - {q(negative)}",
        "boundary_examples:",
        f"  - {q(boundary)}",
        "",
    ])
    return "\n".join(lines)

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output", type=Path, default=Path("research/context_collection/expansion_v3/generated"))
    args = parser.parse_args()
    rows = load_inventory(args.data_dir)
    if args.output.exists():
        shutil.rmtree(args.output)
    args.output.mkdir(parents=True)
    per_category = Counter()
    for row in rows:
        category = str(row[1])
        per_category[category] += 1
        folder = args.output / category
        folder.mkdir(exist_ok=True)
        digest = hashlib.sha1(str(row[0]).encode("utf-8")).hexdigest()[:12]
        path = folder / f"{per_category[category]:04d}_{digest}.yaml"
        path.write_text(yaml_text(row), encoding="utf-8")
    print(json.dumps({"ok": True, "yaml_files": 5000, "category_counts": dict(per_category)}, ensure_ascii=False))

if __name__ == "__main__":
    main()
