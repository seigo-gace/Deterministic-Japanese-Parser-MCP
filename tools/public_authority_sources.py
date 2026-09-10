#!/usr/bin/env python3
"""Normalize reusable public authority resources without inventing definitions."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tempfile
from typing import Any
import zipfile

FIELDS = [
    "subject_heading",
    "reading",
    "authority_id",
    "synonyms",
    "broader_terms",
    "narrower_terms",
    "related_terms",
    "notes",
    "ndlc",
    "ndc9",
    "ndc10",
    "lcsh_reference",
    "bsh4_reference",
    "bsh4_source",
    "sources",
    "edit_history",
    "created_date",
    "updated_date",
]
MULTI_FIELDS = {
    "synonyms",
    "broader_terms",
    "narrower_terms",
    "related_terms",
    "ndlc",
    "ndc9",
    "ndc10",
    "lcsh_reference",
    "bsh4_reference",
    "bsh4_source",
    "sources",
    "edit_history",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def decode_text(payload: bytes) -> tuple[str, str]:
    candidates: list[tuple[int, int, str, str]] = []
    for order, encoding in enumerate(("utf-8-sig", "utf-8", "cp932", "euc_jp")):
        text = payload.decode(encoding, errors="replace")
        candidates.append((text.count("\ufffd"), order, encoding, text))
    _, _, encoding, text = min(candidates)
    return encoding, text


def split_multi(value: str) -> list[str]:
    return [item.strip() for item in value.split("；") if item.strip()]


def source_spec(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sources = manifest.get("sources") or []
    enabled = [s for s in sources if s.get("id") == "web-ndl-authorities-ndlsh" and s.get("status") == "enabled"]
    if len(enabled) != 1:
        raise RuntimeError("NDLSH source spec is not uniquely enabled")
    return enabled[0]


def choose_tsv_member(archive: zipfile.ZipFile) -> zipfile.ZipInfo:
    candidates = [
        info
        for info in archive.infolist()
        if not info.is_dir()
        and PurePosixPath(info.filename).suffix.casefold() in {".txt", ".tsv"}
    ]
    if not candidates:
        raise RuntimeError(f"NDLSH ZIP has no TSV/text member: {archive.namelist()}")
    return max(candidates, key=lambda info: info.file_size)


def _looks_like_header(row: list[str]) -> bool:
    joined = "\t".join(row)
    return any(token in joined for token in ("件名標目", "標目よみ", "同義語", "上位語"))


def normalize(
    manifest_path: Path,
    archive_path: Path,
    output_path: Path,
    report_path: Path,
    lock_path: Path,
) -> dict[str, Any]:
    spec = source_spec(manifest_path)
    source_sha = sha256_file(archive_path)
    with zipfile.ZipFile(archive_path) as archive:
        member = choose_tsv_member(archive)
        payload = archive.read(member)
    encoding, text = decode_text(payload)
    reader = csv.reader(io.StringIO(text), delimiter="\t")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    malformed: list[dict[str, Any]] = []
    records = 0
    synonym_values = 0
    broader_values = 0
    narrower_values = 0
    related_values = 0
    header_detected = False
    with output_path.open("w", encoding="utf-8", newline="\n") as output:
        for source_row_number, row in enumerate(reader, 1):
            if not row or not any(cell.strip() for cell in row):
                continue
            if source_row_number == 1 and _looks_like_header(row):
                header_detected = True
                continue
            if len(row) != 18:
                if len(malformed) < 50:
                    malformed.append(
                        {
                            "source_row_number": source_row_number,
                            "column_count": len(row),
                            "row": row[:25],
                        }
                    )
                continue
            values = {name: row[index].strip() for index, name in enumerate(FIELDS)}
            if not values["subject_heading"] or not values["authority_id"]:
                if len(malformed) < 50:
                    malformed.append(
                        {
                            "source_row_number": source_row_number,
                            "error": "subject heading or authority id missing",
                            "row": row,
                        }
                    )
                continue
            arrays = {
                name: split_multi(values[name])
                for name in MULTI_FIELDS
            }
            synonym_values += len(arrays["synonyms"])
            broader_values += len(arrays["broader_terms"])
            narrower_values += len(arrays["narrower_terms"])
            related_values += len(arrays["related_terms"])
            record = {
                "record_id": f"NDLSH-{values['authority_id']}",
                "surface": values["subject_heading"],
                "reading": values["reading"],
                "authority_id": values["authority_id"],
                "synonyms": arrays["synonyms"],
                "broader_terms": arrays["broader_terms"],
                "narrower_terms": arrays["narrower_terms"],
                "related_terms": arrays["related_terms"],
                "notes": values["notes"],
                "classifications": {
                    "ndlc": arrays["ndlc"],
                    "ndc9": arrays["ndc9"],
                    "ndc10": arrays["ndc10"],
                },
                "references": {
                    "lcsh": arrays["lcsh_reference"],
                    "bsh4": arrays["bsh4_reference"],
                    "bsh4_source": arrays["bsh4_source"],
                },
                "sources": arrays["sources"],
                "edit_history": arrays["edit_history"],
                "created_date": values["created_date"],
                "updated_date": values["updated_date"],
                "source_row_number": source_row_number,
                "source": {
                    "dataset": spec["title"],
                    "source_url": spec["url"],
                    "homepage": spec["homepage"],
                    "source_sha256": source_sha,
                    "reuse_terms": spec["reuse_terms"],
                    "terms_url": spec["terms_url"],
                    "attribution": spec["attribution"],
                },
                "evidence_role": spec["evidence_role"],
                "meaning_policy": spec["meaning_policy"],
            }
            output.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
            records += 1
    if malformed:
        raise RuntimeError(
            f"NDLSH malformed rows detected; count_at_least={len(malformed)} sample={malformed[:10]}"
        )
    if records == 0:
        raise RuntimeError("NDLSH produced zero records")
    normalized_sha = sha256_file(output_path)
    report = {
        "source_id": spec["id"],
        "status": "NORMALIZED",
        "source_sha256": source_sha,
        "source_bytes": archive_path.stat().st_size,
        "zip_member": member.filename,
        "zip_member_bytes": member.file_size,
        "encoding": encoding,
        "header_detected": header_detected,
        "columns": FIELDS,
        "column_count": len(FIELDS),
        "records": records,
        "malformed_records": 0,
        "synonym_values": synonym_values,
        "broader_term_values": broader_values,
        "narrower_term_values": narrower_values,
        "related_term_values": related_values,
        "normalized_path": str(output_path),
        "normalized_sha256": normalized_sha,
        "definition_fabricated": False,
        "llm_api_used": False,
        "web_scraping_used": False,
    }
    lock = {
        "source_id": spec["id"],
        "source_url": spec["url"],
        "source_sha256": source_sha,
        "source_bytes": archive_path.stat().st_size,
        "terms_url": spec["terms_url"],
        "reuse_terms": spec["reuse_terms"],
        "attribution": spec["attribution"],
        "normalized_sha256": normalized_sha,
        "records": records,
        "lock_state": "computed-source-and-normalized-digest",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lock_path.write_text(json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def self_test() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        manifest = root / "manifest.json"
        archive = root / "source.zip"
        output = root / "out.jsonl"
        report = root / "report.json"
        lock = root / "lock.json"
        manifest.write_text(
            json.dumps(
                {
                    "sources": [
                        {
                            "id": "web-ndl-authorities-ndlsh",
                            "title": "test",
                            "status": "enabled",
                            "url": "https://example.invalid/a.zip",
                            "homepage": "https://example.invalid/",
                            "terms_url": "https://example.invalid/terms",
                            "reuse_terms": "test",
                            "attribution": "test",
                            "evidence_role": ["synonym"],
                            "meaning_policy": "relations only",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        header = [
            "件名標目", "標目よみ", "ID", "同義語", "上位語", "下位語", "関連語", "注記",
            "NDLC", "NDC9", "NDC10", "LCSH", "BSH4", "BSH4出典", "出典", "編集履歴", "作成日", "最終更新日"
        ]
        row = [
            "猫", "ネコ", "123", "ねこ；ネコ", "動物<1>", "", "ペット<2>", "注記",
            "RA", "489", "489", "sh1", "b1", "", "資料A；資料B", "", "2000-01-01", "2026-01-01"
        ]
        text = "\t".join(header) + "\n" + "\t".join(row) + "\n"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("ndlsh-test.tsv", text.encode("utf-8"))
        result = normalize(manifest, archive, output, report, lock)
        if result["records"] != 1 or result["column_count"] != 18:
            raise RuntimeError(f"NDLSH self-test failed: {result}")
        obj = json.loads(output.read_text(encoding="utf-8").strip())
        if obj["synonyms"] != ["ねこ", "ネコ"] or obj["broader_terms"] != ["動物<1>"]:
            raise RuntimeError(f"NDLSH self-test relation parsing failed: {obj}")
        return {"status": "PASS", "records": 1, "columns": 18}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--lock", type=Path)
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test(), ensure_ascii=False, sort_keys=True))
        return 0
    required = [args.manifest, args.archive, args.output, args.report, args.lock]
    if any(value is None for value in required):
        parser.error("--manifest --archive --output --report --lock are required")
    result = normalize(args.manifest, args.archive, args.output, args.report, args.lock)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
