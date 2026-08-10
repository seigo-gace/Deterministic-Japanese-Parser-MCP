#!/usr/bin/env python3
"""Inspect and normalize public NICT parallel/translation resources.

Translations are preserved as translation/usage evidence. They are never promoted
by this build tool to monolingual Japanese dictionary definitions.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile
from typing import Any, Iterator
import xml.etree.ElementTree as ET

KNOWN_KYOTO_TAGS = {
    "art", "inf", "tit", "sec", "par", "sen", "j", "e", "cmt", "copyright"
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_report(path: Path, value: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return value


def load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("sources"), list):
        raise RuntimeError("invalid public parallel source manifest")
    return value


def get_spec(manifest: dict[str, Any], source_id: str) -> dict[str, Any]:
    matches = [item for item in manifest["sources"] if item.get("id") == source_id]
    if len(matches) != 1:
        raise RuntimeError(f"source is not unique: {source_id}")
    return matches[0]


def verify_source_digest(spec: dict[str, Any], path: Path) -> str:
    actual = sha256_file(path)
    expected = str(spec.get("expected_source_sha256") or "").strip().casefold()
    if expected and actual.casefold() != expected:
        raise RuntimeError(
            f"source digest mismatch for {spec['id']}: expected={expected} actual={actual}"
        )
    return actual


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
            m
            for m in members
            if any(
                token in PurePosixPath(m.name).name.casefold()
                for token in ("gloss", "lexicon", "term", "yougo", "word")
            )
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
            "llm_api_used": False,
            "web_scraping_used": False,
        }
    return write_report(report_path, report)


def normalize_jecbs(
    spec: dict[str, Any],
    source: Path,
    output_path: Path,
) -> dict[str, Any]:
    try:
        import xlrd
    except ImportError as exc:
        raise RuntimeError("xlrd is required for JECBS normalization") from exc
    source_sha = verify_source_digest(spec, source)
    book = xlrd.open_workbook(str(source), on_demand=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ids: set[str] = set()
    records = 0
    malformed: list[dict[str, Any]] = []
    sheets: list[dict[str, Any]] = []
    with output_path.open("w", encoding="utf-8", newline="\n") as output:
        try:
            for sheet_name in book.sheet_names():
                sheet = book.sheet_by_name(sheet_name)
                sheet_records = 0
                if sheet.ncols != 4:
                    raise RuntimeError(
                        f"JECBS sheet column count changed: {sheet_name} columns={sheet.ncols}"
                    )
                for row_index in range(sheet.nrows):
                    values = [str(sheet.cell_value(row_index, col)).strip() for col in range(4)]
                    if not any(values):
                        continue
                    record_id, japanese, english, chinese = values
                    if not all(values):
                        if len(malformed) < 50:
                            malformed.append(
                                {"sheet": sheet_name, "row": row_index + 1, "values": values}
                            )
                        continue
                    if record_id in ids:
                        raise RuntimeError(f"duplicate JECBS id: {record_id}")
                    ids.add(record_id)
                    record = {
                        "record_id": record_id,
                        "sheet": sheet_name,
                        "source_row_number": row_index + 1,
                        "japanese": japanese,
                        "english": english,
                        "chinese": chinese,
                        "source": {
                            "dataset": spec["title"],
                            "source_url": spec["url"],
                            "homepage": spec["homepage"],
                            "source_sha256": source_sha,
                            "license": spec["license"],
                            "license_url": spec["license_url"],
                            "attribution": spec["attribution"],
                        },
                        "evidence_role": spec["evidence_role"],
                        "semantic_policy": spec["semantic_policy"],
                    }
                    output.write(
                        json.dumps(
                            record,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n"
                    )
                    records += 1
                    sheet_records += 1
                sheets.append(
                    {
                        "name": sheet_name,
                        "source_rows": sheet.nrows,
                        "columns": sheet.ncols,
                        "normalized_records": sheet_records,
                    }
                )
        finally:
            book.release_resources()
    if malformed:
        raise RuntimeError(
            f"JECBS malformed rows: count_at_least={len(malformed)} sample={malformed[:10]}"
        )
    if records != 5304:
        raise RuntimeError(f"JECBS record count changed: expected=5304 actual={records}")
    return {
        "source_id": spec["id"],
        "records": records,
        "sheets": sheets,
        "source_sha256": source_sha,
        "source_bytes": source.stat().st_size,
        "normalized_path": str(output_path),
        "normalized_sha256": sha256_file(output_path),
        "malformed_records": 0,
    }


def text_value(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return "".join(element.itertext()).strip()


def direct_translation_unit(element: ET.Element) -> dict[str, Any] | None:
    japanese_children = [child for child in list(element) if child.tag == "j"]
    if not japanese_children:
        return None
    translations: list[dict[str, Any]] = []
    orphan_comments: list[str] = []
    japanese_values = [text_value(child) for child in japanese_children]
    other_children: list[dict[str, Any]] = []
    last_translation: dict[str, Any] | None = None
    for child in list(element):
        if child.tag == "j":
            continue
        if child.tag == "e":
            item = {
                "type": child.attrib.get("type", ""),
                "version": child.attrib.get("ver", ""),
                "attributes": dict(sorted(child.attrib.items())),
                "text": text_value(child),
                "comments": [],
            }
            translations.append(item)
            last_translation = item
        elif child.tag == "cmt":
            value = text_value(child)
            if last_translation is None:
                orphan_comments.append(value)
            else:
                last_translation["comments"].append(value)
        else:
            other_children.append(
                {
                    "tag": child.tag,
                    "attributes": dict(sorted(child.attrib.items())),
                    "xml": ET.tostring(child, encoding="unicode"),
                }
            )
    return {
        "japanese": japanese_values,
        "translations": translations,
        "orphan_comments": orphan_comments,
        "other_children": other_children,
    }


def walk_elements(element: ET.Element, path: str = "") -> Iterator[tuple[str, ET.Element]]:
    current = path or f"/{element.tag}[1]"
    yield current, element
    counters: Counter[str] = Counter()
    for child in list(element):
        counters[child.tag] += 1
        child_path = f"{current}/{child.tag}[{counters[child.tag]}]"
        yield from walk_elements(child, child_path)


def detect_csv_encoding(payload: bytes) -> tuple[str, str]:
    candidates: list[tuple[int, int, str, str]] = []
    for order, encoding in enumerate(("utf-8-sig", "utf-8", "cp932", "shift_jis", "euc_jp")):
        text = payload.decode(encoding, errors="replace")
        candidates.append((text.count("\ufffd"), order, encoding, text))
    _, _, encoding, text = min(candidates)
    return encoding, text


def looks_japanese(value: str) -> bool:
    return any(
        "\u3040" <= char <= "\u30ff" or "\u3400" <= char <= "\u9fff"
        for char in value
    )


def looks_english(value: str) -> bool:
    letters = sum(char.isascii() and char.isalpha() for char in value)
    return letters >= max(1, len(value.strip()) // 4)


def normalize_kyoto(
    spec: dict[str, Any],
    source: Path,
    output_root: Path,
) -> dict[str, Any]:
    source_sha = verify_source_digest(spec, source)
    output_root.mkdir(parents=True, exist_ok=True)
    article_path = output_root / "kyoto-articles.jsonl"
    unit_path = output_root / "kyoto-translation-units.jsonl"
    lexicon_path = output_root / "kyoto-lexicon.jsonl"
    unknown_path = output_root / "kyoto-unknown-elements.jsonl"

    article_count = 0
    unit_count = 0
    sentence_units = 0
    title_units = 0
    section_units = 0
    missing_translation_units = 0
    tag_counts: Counter[str] = Counter()
    translation_stage_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    unknown_elements = 0
    unknown_examples: list[dict[str, Any]] = []
    glossary_rows = 0
    glossary_field_counts: Counter[int] = Counter()
    glossary_pair_rows = 0
    glossary_encoding = ""
    final_checked_units = 0

    with tarfile.open(source, "r:gz") as archive, article_path.open(
        "w", encoding="utf-8", newline="\n"
    ) as article_out, unit_path.open("w", encoding="utf-8", newline="\n") as unit_out, unknown_path.open(
        "w", encoding="utf-8", newline="\n"
    ) as unknown_out:
        members = [member for member in archive.getmembers() if member.isfile()]
        xml_members = sorted(
            [
                member
                for member in members
                if PurePosixPath(member.name).suffix.casefold() == ".xml"
            ],
            key=lambda member: member.name,
        )
        if len(xml_members) != 14111:
            raise RuntimeError(
                f"Kyoto XML article count changed: expected=14111 actual={len(xml_members)}"
            )
        glossary_members = [
            member
            for member in members
            if PurePosixPath(member.name).name.casefold() == "kyoto_lexicon.csv"
        ]
        if len(glossary_members) != 1:
            raise RuntimeError(
                f"Kyoto glossary member not unique: {[m.name for m in glossary_members]}"
            )

        for article_ordinal, member in enumerate(xml_members, 1):
            handle = archive.extractfile(member)
            if handle is None:
                raise RuntimeError(f"cannot read Kyoto XML member: {member.name}")
            payload = handle.read()
            try:
                root = ET.fromstring(payload)
            except ET.ParseError as exc:
                raise RuntimeError(f"Kyoto XML parse error {member.name}: {exc}") from exc
            if root.tag != "art":
                raise RuntimeError(f"Kyoto XML root changed: {member.name} root={root.tag}")
            category = PurePosixPath(member.name).parts[0]
            category_counts[category] += 1
            article_id = PurePosixPath(member.name).stem
            info_values = [text_value(child) for child in list(root) if child.tag == "inf"]
            copyrights = [
                text_value(child) for child in list(root) if child.tag == "copyright"
            ]
            article_record = {
                "article_ordinal": article_ordinal,
                "article_id": article_id,
                "category": category,
                "archive_member": member.name,
                "root_attributes": dict(sorted(root.attrib.items())),
                "info": info_values,
                "copyright": copyrights,
                "source": {
                    "dataset": spec["title"],
                    "source_url": spec["url"],
                    "homepage": spec["homepage"],
                    "source_sha256": source_sha,
                    "license": spec["license"],
                    "license_url": spec["license_url"],
                    "attribution": spec["attribution"],
                },
            }
            article_out.write(
                json.dumps(
                    article_record,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )
            article_count += 1
            unit_ordinal = 0
            for path, element in walk_elements(root):
                tag_counts[element.tag] += 1
                if element.tag not in KNOWN_KYOTO_TAGS:
                    unknown_elements += 1
                    unknown_record = {
                        "article_id": article_id,
                        "archive_member": member.name,
                        "path": path,
                        "tag": element.tag,
                        "attributes": dict(sorted(element.attrib.items())),
                        "xml": ET.tostring(element, encoding="unicode"),
                    }
                    unknown_out.write(
                        json.dumps(
                            unknown_record,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n"
                    )
                    if len(unknown_examples) < 20:
                        unknown_examples.append(unknown_record)
                unit = direct_translation_unit(element)
                if unit is None:
                    continue
                unit_ordinal += 1
                unit_count += 1
                if element.tag == "sen":
                    sentence_units += 1
                elif element.tag == "tit":
                    title_units += 1
                elif element.tag == "sec":
                    section_units += 1
                if not any(t["text"] for t in unit["translations"]):
                    missing_translation_units += 1
                checked = False
                for translation in unit["translations"]:
                    key = f"{translation['type']}:{translation['version']}"
                    translation_stage_counts[key] += 1
                    if translation["type"] == "check" and translation["text"]:
                        checked = True
                if checked:
                    final_checked_units += 1
                record = {
                    "record_id": f"{article_id}:{unit_ordinal:06d}",
                    "article_id": article_id,
                    "category": category,
                    "archive_member": member.name,
                    "path": path,
                    "element_tag": element.tag,
                    "element_attributes": dict(sorted(element.attrib.items())),
                    **unit,
                    "semantic_policy": spec["semantic_policy"],
                }
                unit_out.write(
                    json.dumps(
                        record,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                )

        glossary_member = glossary_members[0]
        glossary_handle = archive.extractfile(glossary_member)
        if glossary_handle is None:
            raise RuntimeError("cannot read Kyoto glossary")
        glossary_payload = glossary_handle.read()
        glossary_encoding, glossary_text = detect_csv_encoding(glossary_payload)
        rows = list(csv.reader(io.StringIO(glossary_text)))
        nonempty_rows = [row for row in rows if row and any(cell.strip() for cell in row)]
        two_column_rows = [row for row in nonempty_rows if len(row) == 2]
        two_column_semantic = sum(
            1
            for row in two_column_rows[: min(1000, len(two_column_rows))]
            if looks_japanese(row[0]) and looks_english(row[1])
        )
        sample_denominator = min(1000, len(two_column_rows))
        columns_are_ja_en = (
            bool(two_column_rows)
            and sample_denominator > 0
            and two_column_semantic / sample_denominator >= 0.8
        )
        with lexicon_path.open("w", encoding="utf-8", newline="\n") as lexicon_out:
            for row_number, row in enumerate(rows, 1):
                if not row or not any(cell.strip() for cell in row):
                    continue
                values = [cell.strip() for cell in row]
                glossary_rows += 1
                glossary_field_counts[len(values)] += 1
                record: dict[str, Any] = {
                    "record_id": f"kyoto-lexicon:{row_number:07d}",
                    "source_row_number": row_number,
                    "fields": values,
                    "field_count": len(values),
                    "archive_member": glossary_member.name,
                    "semantic_policy": spec["semantic_policy"],
                }
                if columns_are_ja_en and len(values) == 2:
                    record["japanese"] = values[0]
                    record["english"] = values[1]
                    record["evidence_role"] = "bilingual_lexical_translation"
                    glossary_pair_rows += 1
                else:
                    record["evidence_role"] = "raw_glossary_row"
                lexicon_out.write(
                    json.dumps(
                        record,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                )

    if article_count != 14111:
        raise RuntimeError(f"Kyoto article preservation failed: {article_count}")
    if missing_translation_units:
        raise RuntimeError(
            f"Kyoto translation units without translation: {missing_translation_units}"
        )
    if glossary_rows == 0:
        raise RuntimeError("Kyoto glossary produced zero rows")

    files = []
    for path in (article_path, unit_path, lexicon_path, unknown_path):
        files.append(
            {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return {
        "source_id": spec["id"],
        "source_sha256": source_sha,
        "source_bytes": source.stat().st_size,
        "articles": article_count,
        "translation_units": unit_count,
        "sentence_units": sentence_units,
        "title_units": title_units,
        "section_units": section_units,
        "final_checked_units": final_checked_units,
        "missing_translation_units": 0,
        "tag_counts": dict(sorted(tag_counts.items())),
        "translation_stage_counts": dict(sorted(translation_stage_counts.items())),
        "category_counts": dict(sorted(category_counts.items())),
        "unknown_elements": unknown_elements,
        "unknown_examples": unknown_examples,
        "glossary_rows": glossary_rows,
        "glossary_field_count_histogram": {
            str(k): v for k, v in sorted(glossary_field_counts.items())
        },
        "glossary_encoding": glossary_encoding,
        "glossary_columns_identified_as_ja_en": columns_are_ja_en,
        "glossary_bilingual_pair_rows": glossary_pair_rows,
        "files": files,
    }


def normalize_all(
    manifest_path: Path,
    jecbs_source: Path,
    kyoto_source: Path,
    output_root: Path,
    report_path: Path,
    lock_path: Path,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    jecbs_spec = get_spec(manifest, "nict-jec-basic-sentence-v1.2")
    kyoto_spec = get_spec(manifest, "nict-wikipedia-kyoto-corpus-v2.01")
    jecbs = normalize_jecbs(
        jecbs_spec,
        jecbs_source,
        output_root / "jecbs-basic-sentences.jsonl",
    )
    kyoto = normalize_kyoto(
        kyoto_spec,
        kyoto_source,
        output_root / "kyoto",
    )
    report = {
        "schema_version": manifest.get("schema_version"),
        "status": "NORMALIZED",
        "jecbs": jecbs,
        "kyoto": kyoto,
        "definition_fabricated": False,
        "llm_api_used": False,
        "web_scraping_used": False,
    }
    lock = {
        "sources": [
            {
                "source_id": jecbs["source_id"],
                "source_sha256": jecbs["source_sha256"],
                "source_bytes": jecbs["source_bytes"],
                "normalized_sha256": jecbs["normalized_sha256"],
                "records": jecbs["records"],
            },
            {
                "source_id": kyoto["source_id"],
                "source_sha256": kyoto["source_sha256"],
                "source_bytes": kyoto["source_bytes"],
                "files": kyoto["files"],
                "articles": kyoto["articles"],
                "translation_units": kyoto["translation_units"],
                "glossary_rows": kyoto["glossary_rows"],
            },
        ]
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lock_path.write_text(
        json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


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
    p = sub.add_parser("normalize-all")
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--jecbs-source", type=Path, required=True)
    p.add_argument("--kyoto-source", type=Path, required=True)
    p.add_argument("--output-root", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--lock", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "inspect-jecbs":
        result = inspect_jecbs(args.source, args.report)
    elif args.command == "inspect-kyoto":
        result = inspect_kyoto(args.source, args.report, args.sample)
    else:
        result = normalize_all(
            args.manifest,
            args.jecbs_source,
            args.kyoto_source,
            args.output_root,
            args.report,
            args.lock,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
