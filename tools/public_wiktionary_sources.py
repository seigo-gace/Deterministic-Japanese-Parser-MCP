#!/usr/bin/env python3
"""Normalize a source-locked raw Wiktextract snapshot from Japanese Wiktionary.

The raw jawiktionary edition contains entries for many languages. This adapter's
explicit target scope is Modern Japanese (lang_code=ja) and Classical Japanese
(lang_code=ojp). Every raw source line is counted. Every target line is preserved
byte-for-byte (after gzip decompression) in a target preservation stream and is
also emitted as a normalized reference record. Target rows without an actual
Wiktionary gloss are never dropped or assigned an invented meaning; they are
emitted into an unresolved inventory for later evidence review.

No LLM/API inference is used and no record is promoted to Runtime here.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any, BinaryIO
from urllib.parse import quote

TARGET_LANGUAGES = {"ja": "Modern Japanese", "ojp": "Classical Japanese"}
LINKAGE_FIELDS = (
    "antonyms",
    "synonyms",
    "hyponyms",
    "hypernyms",
    "holonyms",
    "meronyms",
    "derived",
    "contraction",
    "abbreviations",
    "related",
    "collocations",
    "proverbs",
    "phrases",
    "coordinate_terms",
    "anagrams",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write_jsonl_gz(handle: BinaryIO, value: dict[str, Any]) -> None:
    handle.write(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        + b"\n"
    )


def clean_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def flatten_glosses(record: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    meanings: list[str] = []
    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()
    senses = record.get("senses")
    if not isinstance(senses, list):
        return meanings, evidence
    for sense_index, sense in enumerate(senses, 1):
        if not isinstance(sense, dict):
            continue
        glosses = sense.get("glosses")
        if not isinstance(glosses, list):
            glosses = []
        sense_glosses: list[str] = []
        for raw_gloss in glosses:
            gloss = clean_text(raw_gloss)
            if not gloss:
                continue
            sense_glosses.append(gloss)
            if gloss not in seen:
                seen.add(gloss)
                meanings.append(gloss)
        if sense_glosses:
            evidence.append(
                {
                    "sense_index": sense_index,
                    "glosses": sense_glosses,
                    "tags": sense.get("tags") if isinstance(sense.get("tags"), list) else [],
                    "raw_tags": sense.get("raw_tags") if isinstance(sense.get("raw_tags"), list) else [],
                    "topics": sense.get("topics") if isinstance(sense.get("topics"), list) else [],
                    "categories": sense.get("categories") if isinstance(sense.get("categories"), list) else [],
                    "examples": sense.get("examples") if isinstance(sense.get("examples"), list) else [],
                    "form_of": sense.get("form_of") if isinstance(sense.get("form_of"), list) else [],
                    "notes": sense.get("notes") if isinstance(sense.get("notes"), list) else [],
                    "ruby": sense.get("ruby") if isinstance(sense.get("ruby"), list) else [],
                }
            )
    return meanings, evidence


def page_url(record: dict[str, Any]) -> str:
    title = clean_text(record.get("title")) or clean_text(record.get("word"))
    return "https://ja.wiktionary.org/wiki/" + quote(title, safe="") if title else ""


def normalized_record(
    record: dict[str, Any],
    *,
    source_row_number: int,
    source_record_sha256: str,
    source_sha256: str,
    source_meta: dict[str, Any],
) -> dict[str, Any]:
    meanings, evidence = flatten_glosses(record)
    lang_code = clean_text(record.get("lang_code"))
    result: dict[str, Any] = {
        "record_id": f"{source_meta['id']}:{source_row_number:09d}",
        "source_row_number": source_row_number,
        "surface": clean_text(record.get("word")),
        "lang_code": lang_code,
        "language_scope": TARGET_LANGUAGES.get(lang_code, ""),
        "language_label": clean_text(record.get("lang")),
        "pos": clean_text(record.get("pos")),
        "pos_title": clean_text(record.get("pos_title")),
        "meanings": meanings,
        "meaning_evidence": evidence,
        "meaning_complete": bool(meanings),
        "forms": record.get("forms") if isinstance(record.get("forms"), list) else [],
        "etymology_texts": record.get("etymology_texts") if isinstance(record.get("etymology_texts"), list) else [],
        "sounds": record.get("sounds") if isinstance(record.get("sounds"), list) else [],
        "translations": record.get("translations") if isinstance(record.get("translations"), list) else [],
        "categories": record.get("categories") if isinstance(record.get("categories"), list) else [],
        "tags": record.get("tags") if isinstance(record.get("tags"), list) else [],
        "raw_tags": record.get("raw_tags") if isinstance(record.get("raw_tags"), list) else [],
        "notes": record.get("notes") if isinstance(record.get("notes"), list) else [],
        "redirect": clean_text(record.get("redirect")),
        "source_record_sha256": source_record_sha256,
        "source_page_url": page_url(record),
        "source": {
            "dataset": source_meta["title"],
            "provider": source_meta["provider"],
            "source_url": source_meta["raw_url"],
            "metadata_url": source_meta["metadata_url"],
            "upstream": source_meta["upstream"],
            "dump_date": source_meta["dump_date"],
            "extraction_date": source_meta["extraction_date"],
            "wiktextract_commits": source_meta["wiktextract_commits"],
            "source_sha256": source_sha256,
            "license": source_meta["license"]["name"],
            "license_url": source_meta["license"]["license_url"],
            "attribution": source_meta["license"]["attribution"],
        },
        "evidence_status": "reference_only",
        "runtime_eligible": False,
        "llm_generated": False,
    }
    for field in LINKAGE_FIELDS:
        result[field] = record.get(field) if isinstance(record.get(field), list) else []
    return result


def normalize(
    source_path: Path,
    output_root: Path,
    report_path: Path,
    lock_path: Path,
    source_meta: dict[str, Any],
) -> dict[str, Any]:
    source_sha = sha256_file(source_path)
    output_root.mkdir(parents=True, exist_ok=True)
    reference_root = output_root / "reference"
    preserved_root = output_root / "preserved"
    unresolved_root = output_root / "unresolved"
    inventory_root = output_root / "inventory"
    for root in (reference_root, preserved_root, unresolved_root, inventory_root):
        root.mkdir(parents=True, exist_ok=True)

    reference_paths = {
        lang: reference_root / f"jawiktionary-{lang}.jsonl.gz" for lang in TARGET_LANGUAGES
    }
    preserved_paths = {
        lang: preserved_root / f"jawiktionary-{lang}.raw.jsonl.gz" for lang in TARGET_LANGUAGES
    }
    unresolved_path = unresolved_root / "jawiktionary-target-missing-gloss.jsonl.gz"
    nontarget_path = inventory_root / "jawiktionary-nontarget-index.jsonl.gz"
    malformed_path = unresolved_root / "jawiktionary-malformed-source-lines.jsonl.gz"

    source_lines = 0
    json_records = 0
    malformed_records = 0
    target_records = 0
    normalized_records = 0
    preserved_records = 0
    missing_gloss_records = 0
    non_target_records = 0
    gloss_count = 0
    sense_count = 0
    example_count = 0
    form_count = 0
    translation_count = 0
    linkage_counts: Counter[str] = Counter()
    lang_counts: Counter[str] = Counter()
    target_lang_counts: Counter[str] = Counter()
    pos_counts: Counter[str] = Counter()
    unique_words: dict[str, set[str]] = {lang: set() for lang in TARGET_LANGUAGES}

    ref_handles = {lang: gzip.open(path, "wb", compresslevel=6) for lang, path in reference_paths.items()}
    preserved_handles = {lang: gzip.open(path, "wb", compresslevel=6) for lang, path in preserved_paths.items()}
    unresolved_handle = gzip.open(unresolved_path, "wb", compresslevel=6)
    nontarget_handle = gzip.open(nontarget_path, "wb", compresslevel=6)
    malformed_handle = gzip.open(malformed_path, "wb", compresslevel=6)
    try:
        with gzip.open(source_path, "rb") as source:
            for source_row_number, raw_line in enumerate(source, 1):
                source_lines += 1
                payload = raw_line.rstrip(b"\r\n")
                if not payload.strip():
                    malformed_records += 1
                    write_jsonl_gz(
                        malformed_handle,
                        {
                            "source_row_number": source_row_number,
                            "error": "empty source line",
                            "source_record_sha256": sha256_bytes(payload),
                        },
                    )
                    continue
                row_sha = sha256_bytes(payload)
                try:
                    record = json.loads(payload.decode("utf-8"))
                except Exception as exc:
                    malformed_records += 1
                    write_jsonl_gz(
                        malformed_handle,
                        {
                            "source_row_number": source_row_number,
                            "error": f"{type(exc).__name__}: {exc}",
                            "source_record_sha256": row_sha,
                            "utf8_preview": payload[:500].decode("utf-8", errors="replace"),
                        },
                    )
                    continue
                if not isinstance(record, dict):
                    malformed_records += 1
                    write_jsonl_gz(
                        malformed_handle,
                        {
                            "source_row_number": source_row_number,
                            "error": "JSON value is not an object",
                            "source_record_sha256": row_sha,
                        },
                    )
                    continue
                json_records += 1
                lang_code = clean_text(record.get("lang_code")) or "<missing>"
                lang_counts[lang_code] += 1
                if lang_code not in TARGET_LANGUAGES:
                    non_target_records += 1
                    write_jsonl_gz(
                        nontarget_handle,
                        {
                            "source_row_number": source_row_number,
                            "lang_code": lang_code,
                            "lang": clean_text(record.get("lang")),
                            "word": clean_text(record.get("word")),
                            "pos": clean_text(record.get("pos")),
                            "source_record_sha256": row_sha,
                        },
                    )
                    continue

                target_records += 1
                target_lang_counts[lang_code] += 1
                word = clean_text(record.get("word"))
                if word:
                    unique_words[lang_code].add(word)
                pos_counts[clean_text(record.get("pos")) or "<missing>"] += 1
                preserved_handles[lang_code].write(payload + b"\n")
                preserved_records += 1

                normalized = normalized_record(
                    record,
                    source_row_number=source_row_number,
                    source_record_sha256=row_sha,
                    source_sha256=source_sha,
                    source_meta=source_meta,
                )
                write_jsonl_gz(ref_handles[lang_code], normalized)
                normalized_records += 1

                meanings = normalized["meanings"]
                gloss_count += len(meanings)
                senses = record.get("senses") if isinstance(record.get("senses"), list) else []
                sense_count += len(senses)
                example_count += sum(
                    len(sense.get("examples"))
                    for sense in senses
                    if isinstance(sense, dict) and isinstance(sense.get("examples"), list)
                )
                form_count += len(record.get("forms")) if isinstance(record.get("forms"), list) else 0
                translation_count += len(record.get("translations")) if isinstance(record.get("translations"), list) else 0
                for field in LINKAGE_FIELDS:
                    values = record.get(field)
                    if isinstance(values, list):
                        linkage_counts[field] += len(values)

                if not meanings:
                    missing_gloss_records += 1
                    write_jsonl_gz(
                        unresolved_handle,
                        {
                            "record_id": normalized["record_id"],
                            "source_row_number": source_row_number,
                            "surface": normalized["surface"],
                            "lang_code": lang_code,
                            "pos": normalized["pos"],
                            "source_page_url": normalized["source_page_url"],
                            "source_record_sha256": row_sha,
                            "reason": "WIKTIONARY_GLOSS_MISSING",
                            "review_status": "needs-evidence",
                            "runtime_eligible": False,
                        },
                    )
    finally:
        for handle in ref_handles.values():
            handle.close()
        for handle in preserved_handles.values():
            handle.close()
        unresolved_handle.close()
        nontarget_handle.close()
        malformed_handle.close()

    output_files: list[dict[str, Any]] = []
    for category, paths in (
        ("reference", reference_paths.values()),
        ("preserved", preserved_paths.values()),
        ("unresolved", (unresolved_path, malformed_path)),
        ("inventory", (nontarget_path,)),
    ):
        for path in paths:
            output_files.append(
                {
                    "category": category,
                    "path": str(path),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )

    preservation_complete = (
        malformed_records == 0
        and source_lines == json_records
        and target_records == normalized_records == preserved_records
        and source_lines == target_records + non_target_records
    )
    report = {
        "schema_version": "1.0.0",
        "status": "NORMALIZED" if preservation_complete else "PARTIAL",
        "source": source_meta,
        "source_bytes": source_path.stat().st_size,
        "source_sha256": source_sha,
        "source_lines": source_lines,
        "json_records": json_records,
        "malformed_records": malformed_records,
        "target_languages": sorted(TARGET_LANGUAGES),
        "target_records": target_records,
        "normalized_records": normalized_records,
        "preserved_records": preserved_records,
        "non_target_records": non_target_records,
        "raw_preservation_complete": preservation_complete,
        "meaning_complete_records": target_records - missing_gloss_records,
        "missing_gloss_records": missing_gloss_records,
        "meaning_complete": missing_gloss_records == 0,
        "gloss_count": gloss_count,
        "sense_count": sense_count,
        "example_count": example_count,
        "form_count": form_count,
        "translation_count": translation_count,
        "linkage_counts": dict(sorted(linkage_counts.items())),
        "language_counts": dict(sorted(lang_counts.items())),
        "target_language_counts": dict(sorted(target_lang_counts.items())),
        "unique_target_words": {lang: len(words) for lang, words in sorted(unique_words.items())},
        "pos_counts": dict(sorted(pos_counts.items())),
        "output_files": output_files,
        "llm_api_used": False,
        "web_scraping_used": False,
        "metadata_page_fetch_used": True,
        "runtime_promotion": False,
        "semantic_policy": (
            "Only actual Wiktionary glosses are treated as lexical meaning evidence. "
            "Missing-gloss target records are preserved and placed in unresolved; no meaning is fabricated."
        ),
    }
    lock = {
        "source_id": source_meta["id"],
        "dump_date": source_meta["dump_date"],
        "extraction_date": source_meta["extraction_date"],
        "source_url": source_meta["raw_url"],
        "source_bytes": source_path.stat().st_size,
        "source_sha256": source_sha,
        "source_lines": source_lines,
        "target_records": target_records,
        "outputs": output_files,
        "license": source_meta["license"],
        "lock_state": "computed-source-and-normalized-digests",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lock_path.write_text(json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def load_source_meta(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "id",
        "title",
        "provider",
        "raw_url",
        "metadata_url",
        "upstream",
        "dump_date",
        "extraction_date",
        "wiktextract_commits",
        "license",
    }
    if not isinstance(value, dict) or not required <= set(value):
        raise RuntimeError(f"invalid source manifest: missing={sorted(required - set(value) if isinstance(value, dict) else required)}")
    if set(value.get("target_lang_codes") or []) != set(TARGET_LANGUAGES):
        raise RuntimeError("target_lang_codes must be exactly ja and ojp")
    license_spec = value.get("license") or {}
    for key in ("name", "license_url", "attribution"):
        if not clean_text(license_spec.get(key)):
            raise RuntimeError(f"license metadata missing: {key}")
    return value


def self_test() -> dict[str, Any]:
    manifest = {
        "id": "jawiktionary-raw-2026-08-04",
        "title": "Japanese Wiktionary raw Wiktextract",
        "provider": "kaikki.org / Wiktextract",
        "raw_url": "https://example.invalid/raw.jsonl.gz",
        "metadata_url": "https://example.invalid/rawdata.html",
        "upstream": "https://ja.wiktionary.org/",
        "dump_date": "2026-08-04",
        "extraction_date": "2026-08-06",
        "wiktextract_commits": ["d9fa233", "9e92f4b"],
        "target_lang_codes": ["ja", "ojp"],
        "license": {
            "name": "CC BY-SA 4.0 / GFDL",
            "license_url": "https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use/ja",
            "attribution": "Japanese Wiktionary page URL retained per record",
        },
    }
    rows = [
        {"word": "猫", "lang_code": "ja", "lang": "日本語", "pos": "noun", "senses": [{"glosses": ["動物の一種"]}]},
        {"word": "あはれ", "lang_code": "ojp", "lang": "古典日本語", "pos": "noun", "senses": [{"glosses": ["しみじみとした情趣"]}]},
        {"word": "cat", "lang_code": "en", "lang": "英語", "pos": "noun", "senses": [{"glosses": ["猫"]}]},
        {"word": "未解決", "lang_code": "ja", "lang": "日本語", "pos": "noun", "senses": []},
    ]
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        source = root / "source.jsonl.gz"
        with gzip.open(source, "wb") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False).encode("utf-8") + b"\n")
        report = normalize(source, root / "out", root / "report.json", root / "lock.json", manifest)
        expected = {
            "source_lines": 4,
            "target_records": 3,
            "normalized_records": 3,
            "preserved_records": 3,
            "non_target_records": 1,
            "missing_gloss_records": 1,
        }
        for key, value in expected.items():
            if report.get(key) != value:
                raise RuntimeError(f"self-test failed: {key}={report.get(key)} expected={value}")
        if report.get("raw_preservation_complete") is not True:
            raise RuntimeError("self-test preservation gate failed")
        return {"status": "PASS", **expected}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--lock", type=Path)
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test(), ensure_ascii=False, sort_keys=True))
        return 0
    required = (args.manifest, args.source, args.output_root, args.report, args.lock)
    if any(value is None for value in required):
        parser.error("--manifest --source --output-root --report --lock are required")
    source_meta = load_source_meta(args.manifest)
    report = normalize(args.source, args.output_root, args.report, args.lock, source_meta)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
