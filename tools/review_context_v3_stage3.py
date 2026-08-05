#!/usr/bin/env python3
"""Stage 3 review triage for Context Data Expansion v3.

This tool never approves or promotes candidates. It validates the complete
candidate inventory, assigns deterministic review flags, and creates small
human-review packs.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_ROOT = ROOT / "research/context_collection/expansion_v3"
DEFAULT_OUTPUT_ROOT = ROOT / "reports/context-v3-stage3"

CATEGORY_ORDER = (
    "slang",
    "onomatopoeia",
    "modality",
    "honorific",
    "discourse",
    "metaphor",
    "dialect",
    "media_community",
    "reference",
    "epistemic",
)

UNKNOWN_LICENSE_MARKERS = (
    "確認中",
    "unknown",
    "unlicensed",
    "private",
    "pending",
    "tbd",
)

NOISY_SOURCE_TAG_MARKERS = (
    "incorrect language header",
    "links with",
    "entries with",
    "terms with 1 kanji",
    "non-redundant non-automated sortkeys",
    "redundant wikilinks",
    "manual fragments",
)

NAME_OR_PLACE_MARKERS = (
    "surname",
    "given name",
    "personal name",
    "place name",
    "neighborhood",
    "prefecture",
    "city in",
    "town in",
    "village in",
    "places in",
)

EPISTEMIC_MARKERS = (
    "かもしれ",
    "かも知れ",
    "かもしん",
    "らしい",
    "ようだ",
    "ようです",
    "そうだ",
    "そうです",
    "はず",
    "可能性",
    "確実",
    "不確実",
    "不明",
    "多分",
    "たぶん",
    "きっと",
    "おそらく",
    "恐らく",
    "噂",
    "うわさ",
    "伝聞",
    "聞いた",
    "聞いて",
    "報道",
    "資料",
    "証拠",
    "とのこと",
    "と思",
    "明らか",
    "気がする",
    "気がします",
)

MODALITY_MARKERS = (
    "してください",
    "して下さい",
    "してくれ",
    "してほしい",
    "して欲しい",
    "してはいけない",
    "してはならない",
    "しないで",
    "するな",
    "しろ",
    "せよ",
    "なさい",
    "べき",
    "必要がある",
    "なくていい",
    "しなくても",
    "してもよい",
    "してもいい",
    "して構わない",
    "差し支えない",
    "てもらえ",
    "ていただ",
    "ませんか",
    "ますか",
    "お願い",
    "禁止",
    "許可",
    "保留",
    "撤回",
    "見送",
    "仮定",
    "可能性",
    "つもり",
    "予定",
    "案もある",
    "方がいい",
    "方がよい",
)

ACTION_MARKERS = (
    "削除",
    "変更",
    "実行",
    "停止",
    "公開",
    "送信",
    "保存",
    "上書き",
    "移動",
    "作成",
    "更新",
    "修正",
    "直す",
    "触る",
    "残す",
    "確認",
    "見る",
    "消す",
    "起動",
    "終了",
)

HONORIFIC_MARKERS = (
    "おっしゃ",
    "いらっしゃ",
    "召し上が",
    "くださ",
    "いただ",
    "頂",
    "参り",
    "参る",
    "伺",
    "申す",
    "申し上げ",
    "存じ",
    "拝",
    "承る",
    "ございます",
    "でございます",
    "なさる",
    "ご覧",
    "お見え",
    "お越し",
    "御",
    "様",
    "さま",
    "殿",
    "先生",
    "社長",
    "部長",
    "課長",
    "弊社",
    "御社",
    "貴社",
)

REFERENCE_MARKERS = (
    "これ",
    "それ",
    "あれ",
    "この",
    "その",
    "あの",
    "こちら",
    "そちら",
    "あちら",
    "前者",
    "後者",
    "同じ",
    "先ほど",
    "さっき",
    "上記",
    "下記",
    "以下",
    "以上",
    "どれ",
    "どちら",
    "何",
    "誰",
    "どこ",
)

DISCOURSE_MARKERS = (
    "あの",
    "えーと",
    "えっと",
    "いや",
    "でも",
    "ただ",
    "だから",
    "なので",
    "それで",
    "さて",
    "要するに",
    "まとめると",
    "そうですね",
    "ですよね",
    "だよね",
    "はい",
    "いいえ",
    "なるほど",
    "ていうか",
    "てか",
    "とはいえ",
    "それはさておき",
    "話を戻",
    "元に戻",
)

METAPHOR_TAG_MARKERS = ("idiom", "proverb", "metaphor", "figurative")
DIALECT_TAG_MARKERS = ("dialect", "regional", "dialectal")
SLANG_TAG_MARKERS = ("slang", "internet", "colloquial", "youth")
ONOMATOPOEIA_TAG_MARKERS = ("onomatopoe", "mimetic", "sound symbolic")
HONORIFIC_TAG_MARKERS = ("honorific", "polite", "respectful", "humble")
DISCOURSE_TAG_MARKERS = ("interjection", "discourse", "particle", "backchannel")
REFERENCE_TAG_MARKERS = ("pronoun", "demonstrative", "determiner", "counter")
MEDIA_TAG_MARKERS = ("gaming", "video game", "fandom", "streaming", "internet")

SAFE_URL_SCHEMES = {"https", "http"}
PRIVATE_URL_MARKERS = ("app.notion.com", "notion.so/", "localhost", "127.0.0.1")


def normalize_surface(value: str) -> str:
    return re.sub(r"\s+", "", str(value)).casefold()


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(f"{key} {_text(item)}" for key, item in value.items())
    return str(value)


def _contains_any(text: str, markers: Iterable[str]) -> bool:
    lowered = text.casefold()
    return any(marker.casefold() in lowered for marker in markers)


def _valid_public_source(source: Any) -> bool:
    if not source:
        return False
    sources = source if isinstance(source, list) else [source]
    for item in sources:
        value = str(item).strip()
        if not value:
            continue
        if any(marker in value.casefold() for marker in PRIVATE_URL_MARKERS):
            return False
        parsed = urlparse(value)
        if parsed.scheme in SAFE_URL_SCHEMES and parsed.netloc:
            return True
        if not parsed.scheme and not value.startswith(("/", "\\")):
            return True
    return False


def load_entries(input_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest_path = input_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths = sorted(
        path
        for category in CATEGORY_ORDER
        for path in (input_root / category).glob("*.yaml")
        if path.name != "index.yaml"
    )
    entries: list[dict[str, Any]] = []
    for path in paths:
        value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(value, dict):
            raise ValueError(f"candidate root must be an object: {path}")
        value["_path"] = str(path.relative_to(input_root))
        entries.append(value)
    return manifest, entries


def validate_inventory(
    manifest: dict[str, Any],
    entries: list[dict[str, Any]],
) -> None:
    expected = int(manifest.get("total_entries", 0))
    if len(entries) != expected:
        raise ValueError(f"candidate count mismatch: expected={expected} actual={len(entries)}")
    entry_ids: set[str] = set()
    surfaces: dict[str, str] = {}
    category_counts: Counter[str] = Counter()
    violations: list[str] = []

    for entry in entries:
        entry_id = str(entry.get("entry_id", "")).strip()
        surface = str(entry.get("surface", "")).strip()
        category = str(entry.get("category", "")).strip()
        if not entry_id or not surface or not category:
            violations.append(f"required field missing: {entry.get('_path')}")
            continue
        if entry_id in entry_ids:
            violations.append(f"duplicate entry_id: {entry_id}")
        entry_ids.add(entry_id)
        normalized = normalize_surface(surface)
        if normalized in surfaces:
            violations.append(
                f"duplicate normalized surface: {surface!r} / {surfaces[normalized]!r}"
            )
        surfaces[normalized] = surface
        category_counts[category] += 1
        if entry.get("review_status") != "needs-evidence":
            violations.append(f"unexpected review_status: {entry_id}")
        if (entry.get("provenance") or {}).get("meaning_promotion_allowed") is not False:
            violations.append(f"meaning promotion boundary missing: {entry_id}")

    expected_counts = {
        key: int(value)
        for key, value in (manifest.get("category_counts") or {}).items()
    }
    if dict(sorted(category_counts.items())) != dict(sorted(expected_counts.items())):
        violations.append(
            f"category counts mismatch: expected={expected_counts} "
            f"actual={dict(category_counts)}"
        )
    if manifest.get("runtime_promotion_allowed") is not False:
        violations.append("manifest runtime_promotion_allowed must be false")
    if manifest.get("semantic_completion_claim_allowed") is not False:
        violations.append("manifest semantic_completion_claim_allowed must be false")
    if violations:
        raise ValueError("; ".join(violations[:20]))


def _category_flags(entry: dict[str, Any]) -> set[str]:
    category = str(entry.get("category", ""))
    surface = str(entry.get("surface", ""))
    feature_type = str(entry.get("feature_type", ""))
    provenance = entry.get("provenance") or {}
    origin = str(provenance.get("origin", ""))
    tags = _text(provenance.get("source_tags", []))
    source_pos = str(provenance.get("source_pos", "") or "")
    meanings = _text(entry.get("meaning_candidates", []))
    combined = f"{surface} {tags} {source_pos} {meanings}"
    flags: set[str] = set()

    if feature_type and category == "epistemic" and feature_type != "modality":
        flags.add("feature-type-mismatch")
    elif feature_type and category != "epistemic" and feature_type != category:
        flags.add("feature-type-mismatch")

    if _contains_any(tags, NOISY_SOURCE_TAG_MARKERS):
        flags.add("source-metadata-noise")
    if source_pos.casefold() in {"name", "proper noun", "surname"} or _contains_any(
        combined, NAME_OR_PLACE_MARKERS
    ):
        flags.add("name-or-place-candidate")

    if category == "epistemic":
        if "かも" in surface and not _contains_any(surface, EPISTEMIC_MARKERS):
            flags.add("substring-artifact")
        if not _contains_any(surface, EPISTEMIC_MARKERS):
            flags.add("category-evidence-missing")
    elif category == "modality":
        if not _contains_any(surface, MODALITY_MARKERS):
            flags.add("category-evidence-missing")
        if _contains_any(surface, ACTION_MARKERS):
            flags.add("external-action-review-required")
    elif category == "dialect":
        if not _contains_any(tags, DIALECT_TAG_MARKERS) and origin != "existing-v2-candidate":
            flags.add("category-evidence-missing")
    elif category == "honorific":
        if not _contains_any(surface, HONORIFIC_MARKERS) and not _contains_any(
            tags, HONORIFIC_TAG_MARKERS
        ):
            flags.add("category-evidence-missing")
    elif category == "discourse":
        if not _contains_any(surface, DISCOURSE_MARKERS) and not _contains_any(
            tags, DISCOURSE_TAG_MARKERS
        ):
            flags.add("category-evidence-missing")
    elif category == "metaphor":
        multiword = len(surface) >= 4 and any(
            marker in surface
            for marker in ("を", "に", "が", "は", "も", "より", "れば", "なら")
        )
        if not multiword and not _contains_any(tags, METAPHOR_TAG_MARKERS):
            flags.add("category-evidence-missing")
    elif category == "reference":
        if not _contains_any(surface, REFERENCE_MARKERS) and not _contains_any(
            tags, REFERENCE_TAG_MARKERS
        ):
            flags.add("category-evidence-missing")
    elif category == "slang":
        if origin != "living-japanese-slang-dictionary" and not _contains_any(
            tags, SLANG_TAG_MARKERS
        ):
            flags.add("category-evidence-missing")
    elif category == "onomatopoeia":
        if origin != "j-ono-data" and not _contains_any(
            tags, ONOMATOPOEIA_TAG_MARKERS
        ):
            flags.add("category-evidence-missing")
    elif category == "media_community":
        if not _contains_any(combined, MEDIA_TAG_MARKERS) and origin not in {
            "existing-v2-candidate",
            "living-japanese-slang-dictionary",
        }:
            flags.add("category-evidence-missing")

    return flags


def classify_entry(entry: dict[str, Any]) -> dict[str, Any]:
    entry_id = str(entry["entry_id"])
    surface = str(entry["surface"])
    category = str(entry["category"])
    provenance = entry.get("provenance") or {}
    license_value = str(entry.get("license", "")).strip()
    flags = _category_flags(entry)

    if any(marker.casefold() in license_value.casefold() for marker in UNKNOWN_LICENSE_MARKERS):
        flags.add("license-review-required")
    if not _valid_public_source(entry.get("source")):
        flags.add("public-source-missing")
    if provenance.get("constructed_examples") is True:
        flags.add("direct-occurrence-evidence-required")
    if not entry.get("positive_examples"):
        flags.add("positive-example-missing")
    if not entry.get("negative_examples"):
        flags.add("negative-example-missing")
    if not entry.get("boundary_examples"):
        flags.add("boundary-example-missing")
    if entry.get("external_action_risk") is True:
        flags.add("external-action-review-required")

    if "license-review-required" in flags or "public-source-missing" in flags:
        primary_status = "blocked-source-or-license"
    elif "substring-artifact" in flags:
        primary_status = "suspected-substring-artifact"
    elif flags.intersection(
        {"category-evidence-missing", "feature-type-mismatch", "name-or-place-candidate"}
    ):
        primary_status = "suspected-category-mismatch"
    elif "external-action-review-required" in flags:
        primary_status = "high-risk-action-review"
    else:
        primary_status = "ready-for-human-evidence-review"

    return {
        "entry_id": entry_id,
        "surface": surface,
        "category": category,
        "feature_type": entry.get("feature_type"),
        "path": entry["_path"],
        "origin": provenance.get("origin"),
        "license": license_value,
        "primary_status": primary_status,
        "flags": sorted(flags),
        "runtime_promotion_allowed": False,
    }


def _json_line(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_reports(
    manifest: dict[str, Any],
    entries: list[dict[str, Any]],
    *,
    pack_size: int,
) -> dict[str, str]:
    records = [classify_entry(entry) for entry in entries]
    records.sort(key=lambda item: (CATEGORY_ORDER.index(item["category"]), item["entry_id"]))

    status_counts = Counter(item["primary_status"] for item in records)
    flag_counts = Counter(flag for item in records for flag in item["flags"])
    category_status: dict[str, Counter[str]] = defaultdict(Counter)
    origin_counts = Counter(str(item["origin"]) for item in records)
    license_counts = Counter(item["license"] for item in records)
    for item in records:
        category_status[item["category"]][item["primary_status"]] += 1

    packs: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in records:
        grouped[(item["category"], item["primary_status"])].append(item)
    for category in CATEGORY_ORDER:
        statuses = sorted(status for cat, status in grouped if cat == category)
        for status in statuses:
            items = grouped[(category, status)]
            for start in range(0, len(items), pack_size):
                batch = items[start : start + pack_size]
                pack_number = start // pack_size + 1
                packs.append({
                    "pack_id": (
                        f"{category.upper()}-{status.upper().replace('-', '_')}-"
                        f"{pack_number:03d}"
                    ),
                    "category": category,
                    "primary_status": status,
                    "entry_count": len(batch),
                    "entry_ids": [item["entry_id"] for item in batch],
                    "surfaces": [item["surface"] for item in batch],
                    "required_checks": [
                        "direct occurrence evidence",
                        "independent meaning and context evidence",
                        "source version and license",
                        "reading and variants",
                        "positive, negative, and boundary cases",
                        "quotation, negation, question, hypothesis, and hearsay",
                        "external-action risk when applicable",
                        "human decision",
                    ],
                    "runtime_promotion_allowed": False,
                })

    summary_core = {
        "schema_version": "1.0.0",
        "source_collection_version": manifest.get("collection_version"),
        "source_manifest_sha256": hashlib.sha256(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "total_entries": len(records),
        "reviewed_or_approved_entries": 0,
        "runtime_promoted_entries": 0,
        "pack_size": pack_size,
        "pack_count": len(packs),
        "status_counts": dict(sorted(status_counts.items())),
        "flag_counts": dict(sorted(flag_counts.items())),
        "category_status_counts": {
            category: dict(sorted(category_status[category].items()))
            for category in CATEGORY_ORDER
        },
        "origin_counts": dict(sorted(origin_counts.items())),
        "license_counts": dict(sorted(license_counts.items())),
        "stage3_boundary": {
            "automatic_approval": False,
            "automatic_rejection": False,
            "runtime_promotion": False,
            "semantic_completion_claim": False,
            "human_review_required": True,
        },
    }
    queue_text = "".join(_json_line(item) + "\n" for item in records)
    packs_text = "".join(_json_line(item) + "\n" for item in packs)
    summary_core["review_queue_sha256"] = hashlib.sha256(
        queue_text.encode("utf-8")
    ).hexdigest()
    summary_core["review_packs_sha256"] = hashlib.sha256(
        packs_text.encode("utf-8")
    ).hexdigest()

    boundary = {
        "stage": 3,
        "name": "evidence, category, collision, and safety review",
        "input_entries": len(records),
        "approved_entries": 0,
        "runtime_promoted_entries": 0,
        "forbidden_transitions": [
            "candidate to semantic sense without evidence",
            "candidate to intent or task automatically",
            "candidate to external action automatically",
            "community vote to runtime promotion",
        ],
        "next_transition": (
            "human-reviewed entries with source, license, meaning, context, "
            "positive/negative/boundary tests, holdout, and safety approval"
        ),
    }

    return {
        "summary.json": json.dumps(
            summary_core, ensure_ascii=False, indent=2, sort_keys=True
        ) + "\n",
        "review-queue.jsonl": queue_text,
        "review-packs.jsonl": packs_text,
        "runtime-boundary.json": json.dumps(
            boundary, ensure_ascii=False, indent=2, sort_keys=True
        ) + "\n",
    }


def write_reports(output_root: Path, files: dict[str, str]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    expected = set(files)
    for path in output_root.iterdir():
        if path.is_file() and path.name not in expected:
            path.unlink()
    for name, content in files.items():
        (output_root / name).write_text(content, encoding="utf-8", newline="\n")


def check_reports(output_root: Path, files: dict[str, str]) -> None:
    actual = {
        path.name for path in output_root.iterdir() if path.is_file()
    } if output_root.exists() else set()
    if actual != set(files):
        raise RuntimeError(
            f"Stage 3 report file set is stale: expected={sorted(files)} "
            f"actual={sorted(actual)}"
        )
    for name, expected in files.items():
        value = (output_root / name).read_text(encoding="utf-8")
        if value != expected:
            raise RuntimeError(f"Stage 3 report is stale: {name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--pack-size", type=int, default=20)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.pack_size <= 100:
        raise ValueError("pack-size must be between 1 and 100")

    manifest, entries = load_entries(args.input_root)
    validate_inventory(manifest, entries)
    files = build_reports(manifest, entries, pack_size=args.pack_size)
    if args.check:
        check_reports(args.output_root, files)
        action = "CHECKED"
    else:
        write_reports(args.output_root, files)
        action = "WRITTEN"
    summary = json.loads(files["summary.json"])
    print(json.dumps({
        "status": action,
        "entries": summary["total_entries"],
        "packs": summary["pack_count"],
        "status_counts": summary["status_counts"],
        "runtime_promoted_entries": 0,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
