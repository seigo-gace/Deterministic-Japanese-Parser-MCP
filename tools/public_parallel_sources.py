#!/usr/bin/env python3
"""Inspect public NICT parallel/translation resources from their real structures."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
from typing import Any


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_report(path: Path, value: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return value


def inspect_jecbs(source: Path, report_path: Path) -> dict[str, Any]:
    try:
        import xlrd
    except ImportError as exc:
        raise RuntimeError("xlrd is required for legacy XLS inspection") from exc
    book = xlrd.open_workbook(str(source), on_demand=True)
    sheets: list[dict[str, Any]] = []
    try:
        for sheet_name in book.sheet_names():
            sheet = book.sheet_by_name(sheet_name)
            samples: list[dict[str, Any]] = []
            for row_index in range(min(sheet.nrows, 100)):
                values = [sheet.cell_value(row_index, col) for col in range(sheet.ncols)]
                if not any(str(value).strip() for value in values):
                    continue
                samples.append({"row": row_index + 1, "values": values})
                if len(samples) >= 30:
                    break
            sheets.append(
                {
                    "name": sheet_name,
                    "rows": sheet.nrows,
                    "columns": sheet.ncols,
                    "sample_nonempty_rows": samples,
                }
            )
    finally:
        book.release_resources()
    report = {
        "source_id": "nict-jec-basic-sentence-v1.2",
        "status": "SOURCE_ACQUIRED_STRUCTURE_INSPECTED",
        "source_bytes": source.stat().st_size,
        "source_sha256": sha256_file(source),
        "workbook_sheets": sheets,
        "llm_api_used": False,
        "web_scraping_used": False,
    }
    return write_report(report_path, report)


def inspect_kyoto(source: Path, report_path: Path, sample_path: Path) -> dict[str, Any]:
    with tarfile.open(source, "r:gz") as archive:
        members = [m for m in archive.getmembers() if m.isfile()]
        xml_members = [m for m in members if PurePosixPath(m.name).suffix.casefold() == ".xml"]
        pdf_members = [m for m in members if PurePosixPath(m.name).suffix.casefold() == ".pdf"]
        glossary_candidates = [
            m for m in members
            if any(token in PurePosixPath(m.name).name.casefold() for token in ("gloss", "lexicon", "term", "yougo", "word"))
        ]
        if not xml_members:
            raise RuntimeError("Kyoto corpus archive contains no XML files")
        first_xml = xml_members[0]
        handle = archive.extractfile(first_xml)
        if handle is None:
            raise RuntimeError("cannot read Kyoto sample XML")
        payload = handle.read(256 * 1024)
        text = payload.decode("utf-8", errors="replace")
        sample_path.parent.mkdir(parents=True, exist_ok=True)
        sample_path.write_text(text, encoding="utf-8")
        member_sample = [
            {"name": member.name, "bytes": member.size}
            for member in members[:100]
        ]
        report = {
            "source_id": "nict-wikipedia-kyoto-corpus-v2.01",
            "status": "SOURCE_ACQUIRED_STRUCTURE_INSPECTED",
            "source_bytes": source.stat().st_size,
            "source_sha256": sha256_file(source),
            "file_members": len(members),
            "xml_members": len(xml_members),
            "pdf_members": [m.name for m in pdf_members],
            "glossary_candidates": [m.name for m in glossary_candidates[:100]],
            "first_xml_member": first_xml.name,
            "sample_sha256": sha256_file(sample_path),
            "member_sample": member_sample,
            "llm_api_used": False,
            "web_scraping_used": False,
        }
    return write_report(report_path, report)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("inspect-jecbs")
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    p = sub.add_parser("inspect-kyoto")
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--sample", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "inspect-jecbs":
        result = inspect_jecbs(args.source, args.report)
    else:
        result = inspect_kyoto(args.source, args.report, args.sample)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
