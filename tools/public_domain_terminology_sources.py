#!/usr/bin/env python3
"""Normalize NBDC science/medical/chemical MeCab terminology dictionaries.

These archives are domain/morphology evidence. The source explicitly says term
relations are not present, so this adapter never manufactures synonym or definition
edges. Empty reading/pronunciation fields remain empty and source identifiers are
retained for later semantic evidence joins.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tempfile
from typing import Any
import zipfile

FIELDS = [
    "surface",
    "left_context_id",
    "right_context_id",
    "cost",
    "pos",
    "pos_subcategory_1",
    "pos_subcategory_2",
    "pos_subcategory_3",
    "conjugation_type",
    "conjugation_form",
    "base_form",
    "reading",
    "pronunciation",
    "source_dictionary",
    "source_dictionary_id",
    "jglobal_id",
    "headword_flag",
    "category_code",
    "common_word_flag_1",
    "common_word_flag_2",
    "ipa_dictionary_analysis",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("sources"), list):
        raise RuntimeError("invalid domain terminology manifest")
    return value


def select_member(archive: zipfile.ZipFile) -> zipfile.ZipInfo:
    files = [info for info in archive.infolist() if not info.is_dir()]
    candidates = [
        info for info in files
        if PurePosixPath(info.filename).suffix.casefold() in {".dic", ".csv", ".txt"}
    ]
    if not candidates:
        raise RuntimeError(f"no dictionary member found: {archive.namelist()}")
    return max(candidates, key=lambda info: info.file_size)


def decode_payload(payload: bytes) -> tuple[str, str]:
    candidates: list[tuple[int, int, str, str]] = []
    for order, encoding in enumerate(("utf-8-sig", "utf-8", "cp932", "shift_jis", "euc_jp")):
        text = payload.decode(encoding, errors="replace")
        candidates.append((text.count("\ufffd"), order, encoding, text))
    _, _, encoding, text = min(candidates)
    return encoding, text


def normalize_one(
    spec: dict[str, Any],
    license_spec: dict[str, Any],
    archive_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    source_sha = sha256_file(archive_path)
    with zipfile.ZipFile(archive_path) as archive:
        member = select_member(archive)
        payload = archive.read(member)
    encoding, text = decode_payload(payload)
    reader = csv.reader(io.StringIO(text))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    records = 0
    empty_reading = 0
    empty_pronunciation = 0
    source_dictionary_values: Counter[str] = Counter()
    headword_flags: Counter[str] = Counter()
    category_values: Counter[str] = Counter()
    malformed: list[dict[str, Any]] = []
    with output_path.open("w", encoding="utf-8", newline="\n") as output:
        for source_row_number, row in enumerate(reader, 1):
            if not row or not any(cell.strip() for cell in row):
                continue
            if len(row) != len(FIELDS):
                if len(malformed) < 50:
                    malformed.append(
                        {
                            "source_row_number": source_row_number,
                            "field_count": len(row),
                            "sample": row[:30],
                        }
                    )
                continue
            values = {field: row[index].strip() for index, field in enumerate(FIELDS)}
            if not values["surface"]:
                if len(malformed) < 50:
                    malformed.append(
                        {"source_row_number": source_row_number, "error": "empty surface"}
                    )
                continue
            if not values["reading"]:
                empty_reading += 1
            if not values["pronunciation"]:
                empty_pronunciation += 1
            source_dictionary_values[values["source_dictionary"]] += 1
            headword_flags[values["headword_flag"]] += 1
            if values["category_code"]:
                for category in values["category_code"].split("|"):
                    if category.strip():
                        category_values[category.strip()] += 1
            record = {
                "record_id": f"{spec['id']}:{source_row_number:09d}",
                "source_row_number": source_row_number,
                **values,
                "domain": spec.get("domain") or [],
                "source": {
                    "dataset": spec["title"],
                    "source_url": spec["url"],
                    "homepage": spec["homepage"],
                    "source_sha256": source_sha,
                    "license": license_spec["name"],
                    "license_url": license_spec["license_url"],
                    "terms_url": license_spec["terms_url"],
                    "attribution": license_spec["attribution"],
                },
                "semantic_policy": (
                    "domain/morphology terminology evidence only; no fabricated "
                    "definition or term-to-term relation"
                ),
            }
            output.write(
                json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n"
            )
            records += 1
    if malformed:
        raise RuntimeError(
            f"terminology source has malformed rows: count_at_least={len(malformed)} "
            f"sample={malformed[:10]}"
        )
    if records == 0:
        raise RuntimeError("terminology source produced no records")
    return {
        "source_id": spec["id"],
        "records": records,
        "source_sha256": source_sha,
        "source_bytes": archive_path.stat().st_size,
        "zip_member": member.filename,
        "zip_member_bytes": member.file_size,
        "encoding": encoding,
        "field_count": len(FIELDS),
        "empty_reading_records": empty_reading,
        "empty_pronunciation_records": empty_pronunciation,
        "source_dictionary_counts": dict(sorted(source_dictionary_values.items())),
        "headword_flag_counts": dict(sorted(headword_flags.items())),
        "category_code_counts": dict(sorted(category_values.items())),
        "normalized_path": str(output_path),
        "normalized_sha256": sha256_file(output_path),
        "definition_fabricated": False,
        "term_relations_fabricated": False,
    }


def normalize_all(
    manifest_path: Path,
    source_root: Path,
    output_root: Path,
    report_path: Path,
    lock_path: Path,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    license_spec = manifest.get("license") or {}
    required_license = {"name", "license_url", "terms_url", "attribution"}
    if not required_license <= set(license_spec):
        raise RuntimeError("license metadata is incomplete")
    reports: list[dict[str, Any]] = []
    for spec in manifest["sources"]:
        if spec.get("status") != "enabled":
            continue
        source_path = source_root / f"{spec['id']}.zip"
        if not source_path.is_file():
            raise RuntimeError(f"source archive missing: {source_path}")
        output_path = output_root / f"{spec['id']}.jsonl"
        reports.append(normalize_one(spec, license_spec, source_path, output_path))
    if not reports:
        raise RuntimeError("no enabled terminology sources")
    report = {
        "schema_version": manifest.get("schema_version"),
        "status": "NORMALIZED",
        "source_count": len(reports),
        "total_records": sum(item["records"] for item in reports),
        "field_count": len(FIELDS),
        "fields": FIELDS,
        "sources": reports,
        "license": license_spec,
        "semantic_policy": manifest.get("semantic_policy"),
        "definition_fabricated": False,
        "term_relations_fabricated": False,
        "llm_api_used": False,
        "web_scraping_used": False,
    }
    locks = {
        "license": license_spec,
        "sources": [
            {
                "source_id": item["source_id"],
                "source_sha256": item["source_sha256"],
                "source_bytes": item["source_bytes"],
                "normalized_sha256": item["normalized_sha256"],
                "records": item["records"],
                "lock_state": "computed-source-and-normalized-digest",
            }
            for item in reports
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lock_path.write_text(json.dumps(locks, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def self_test() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        manifest = root / "manifest.json"
        source_root = root / "source"
        output_root = root / "out"
        source_root.mkdir()
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": "1",
                    "license": {
                        "name": "CC BY-SA 4.0",
                        "license_url": "x",
                        "terms_url": "y",
                        "attribution": "z",
                    },
                    "sources": [
                        {
                            "id": "test",
                            "title": "test",
                            "status": "enabled",
                            "url": "x",
                            "homepage": "y",
                            "domain": ["science"],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        row = [
            "量子", "1", "1", "100", "名詞", "一般", "*", "*", "*", "*", "量子",
            "リョウシ", "リョーシ", "Thesaurus2015", "T1", "JG1", "C", "PA01", "1", "名詞", "量子/名詞"
        ]
        archive_path = source_root / "test.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            buffer = io.StringIO()
            csv.writer(buffer, lineterminator="\n").writerow(row)
            archive.writestr("test.dic", buffer.getvalue().encode("utf-8"))
        report = normalize_all(manifest, source_root, output_root, root / "report.json", root / "lock.json")
        if report["total_records"] != 1 or report["field_count"] != 21:
            raise RuntimeError(f"self-test failed: {report}")
        return {"status": "PASS", "records": 1, "fields": 21}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--lock", type=Path)
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test(), ensure_ascii=False, sort_keys=True))
        return 0
    if any(value is None for value in (args.manifest, args.source_root, args.output_root, args.report, args.lock)):
        parser.error("--manifest --source-root --output-root --report --lock are required")
    result = normalize_all(args.manifest, args.source_root, args.output_root, args.report, args.lock)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
