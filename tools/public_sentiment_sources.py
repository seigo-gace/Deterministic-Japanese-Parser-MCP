#!/usr/bin/env python3
"""Normalize Tohoku University Japanese sentiment polarity dictionaries.

Polarity is preserved as an overlay; it is never treated as a lexical definition.
Every non-empty source line is represented either as a data record or as a source
section/header row so the adapter cannot silently discard source structure.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def decode(path: Path) -> tuple[str, str]:
    payload = path.read_bytes()
    candidates: list[tuple[int, int, str, str]] = []
    for order, encoding in enumerate(("utf-8-sig", "utf-8", "cp932", "euc_jp")):
        text = payload.decode(encoding, errors="replace")
        candidates.append((text.count("\ufffd"), order, encoding, text))
    _, _, encoding, text = min(candidates)
    return encoding, text


def load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("sources"), list):
        raise RuntimeError("invalid sentiment source manifest")
    return value


def spec_by_id(manifest: dict[str, Any], source_id: str) -> dict[str, Any]:
    matches = [item for item in manifest["sources"] if item.get("id") == source_id]
    if len(matches) != 1:
        raise RuntimeError(f"sentiment source not unique: {source_id}")
    return matches[0]


def source_meta(spec: dict[str, Any], source_sha: str) -> dict[str, Any]:
    return {
        "dataset": spec["title"],
        "version": spec["version"],
        "source_url": spec["url"],
        "homepage": spec["homepage"],
        "source_sha256": source_sha,
        "author": spec["author"],
        "commercial_use": spec["commercial_use"],
        "citation": spec["citation"],
    }


def normalize_predicate(
    spec: dict[str, Any], source: Path, output: Path
) -> dict[str, Any]:
    encoding, text = decode(source)
    source_sha = sha256_file(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    nonempty_source_lines = 0
    data_records = 0
    section_rows = 0
    malformed: list[dict[str, Any]] = []
    polarity_counts: Counter[str] = Counter()
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        for line_number, raw in enumerate(text.splitlines(), 1):
            if not raw.strip():
                continue
            nonempty_source_lines += 1
            fields = raw.split("\t")
            label = fields[0].strip() if fields else ""
            tail = "\t".join(fields[1:]).strip() if len(fields) >= 2 else ""

            # The published predicate dictionary contains section labels in both
            # one-field form and "label<TAB>" form. A trailing empty field is
            # source structure, not a malformed sentiment expression.
            if label and (len(fields) == 1 or not tail):
                record = {
                    "record_type": "section",
                    "source_line_number": line_number,
                    "label": label,
                    "raw_fields": fields,
                    "raw_line": raw,
                    "source": source_meta(spec, source_sha),
                }
                section_rows += 1
            elif len(fields) >= 2:
                polarity = label
                expression = tail
                if not polarity or not expression:
                    if len(malformed) < 50:
                        malformed.append(
                            {"line": line_number, "fields": fields, "raw": raw}
                        )
                    continue
                record = {
                    "record_type": "sentiment_expression",
                    "record_id": f"PRED-{line_number:06d}",
                    "source_line_number": line_number,
                    "expression": expression,
                    "polarity_label": polarity,
                    "raw_fields": fields,
                    "raw_line": raw,
                    "evidence_role": spec["evidence_role"],
                    "source": source_meta(spec, source_sha),
                    "semantic_policy": "sentiment overlay only; lexical meaning not generated",
                }
                data_records += 1
                polarity_counts[polarity] += 1
            else:
                if len(malformed) < 50:
                    malformed.append(
                        {"line": line_number, "fields": fields, "raw": raw}
                    )
                continue
            handle.write(
                json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n"
            )
    if malformed:
        raise RuntimeError(
            f"predicate sentiment malformed rows: count_at_least={len(malformed)} sample={malformed[:10]}"
        )
    if data_records + section_rows != nonempty_source_lines:
        raise RuntimeError(
            f"predicate source line loss: source={nonempty_source_lines} data={data_records} section={section_rows}"
        )
    return {
        "source_id": spec["id"],
        "source_sha256": source_sha,
        "source_bytes": source.stat().st_size,
        "encoding": encoding,
        "nonempty_source_lines": nonempty_source_lines,
        "data_records": data_records,
        "section_rows": section_rows,
        "polarity_counts": dict(sorted(polarity_counts.items())),
        "malformed_records": 0,
        "normalized_sha256": sha256_file(output),
        "normalized_path": str(output),
    }


def normalize_noun(
    spec: dict[str, Any], source: Path, output: Path
) -> dict[str, Any]:
    encoding, text = decode(source)
    source_sha = sha256_file(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter="\t")
    nonempty_source_rows = 0
    records = 0
    unlabeled_records = 0
    field_counts: Counter[int] = Counter()
    polarity_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    malformed: list[dict[str, Any]] = []
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        for row_number, row in enumerate(reader, 1):
            if not row or not any(cell.strip() for cell in row):
                continue
            nonempty_source_rows += 1
            values = [cell.strip() for cell in row]
            field_counts[len(values)] += 1
            if len(values) != 3:
                if len(malformed) < 50:
                    malformed.append(
                        {"row": row_number, "field_count": len(values), "fields": values}
                    )
                continue
            term, polarity, semantic_category = values
            if not term:
                if len(malformed) < 50:
                    malformed.append(
                        {"row": row_number, "error": "term empty", "fields": values}
                    )
                continue

            if polarity:
                record_type = "noun_sentiment"
                review_status = "source-labeled"
                polarity_counts[polarity] += 1
            else:
                # The published noun dictionary contains a source-authored row
                # with an empty polarity field. Preserve it exactly rather than
                # dropping it or inventing a polarity label.
                record_type = "noun_unlabeled"
                review_status = "needs-evidence"
                unlabeled_records += 1

            record = {
                "record_type": record_type,
                "record_id": f"NOUN-{row_number:06d}",
                "source_row_number": row_number,
                "term": term,
                "polarity_label": polarity,
                "semantic_category": semantic_category,
                "raw_fields": values,
                "review_status": review_status,
                "evidence_role": spec["evidence_role"],
                "source": source_meta(spec, source_sha),
                "semantic_policy": (
                    "sentiment and published semantic-category overlay only; "
                    "not a standalone lexical definition; empty source polarity is preserved and never inferred"
                ),
            }
            handle.write(
                json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n"
            )
            records += 1
            category_counts[semantic_category] += 1
    if malformed:
        raise RuntimeError(
            f"noun sentiment source structure changed: count_at_least={len(malformed)} "
            f"field_histogram={dict(sorted(field_counts.items()))} sample={malformed[:10]}"
        )
    if records != nonempty_source_rows:
        raise RuntimeError(
            f"noun sentiment source row loss: source={nonempty_source_rows} records={records}"
        )
    return {
        "source_id": spec["id"],
        "source_sha256": source_sha,
        "source_bytes": source.stat().st_size,
        "encoding": encoding,
        "nonempty_source_rows": nonempty_source_rows,
        "records": records,
        "unlabeled_records": unlabeled_records,
        "field_count_histogram": {str(k): v for k, v in sorted(field_counts.items())},
        "polarity_counts": dict(sorted(polarity_counts.items())),
        "semantic_category_counts": dict(sorted(category_counts.items())),
        "malformed_records": 0,
        "normalized_sha256": sha256_file(output),
        "normalized_path": str(output),
    }


def normalize_all(
    manifest_path: Path,
    predicate_source: Path,
    noun_source: Path,
    output_root: Path,
    report_path: Path,
    lock_path: Path,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    pred_spec = spec_by_id(manifest, "tohoku-sentiment-predicate-v1.0")
    noun_spec = spec_by_id(manifest, "tohoku-sentiment-noun-v1.0")
    predicate = normalize_predicate(
        pred_spec, predicate_source, output_root / "predicate-sentiment.jsonl"
    )
    noun = normalize_noun(noun_spec, noun_source, output_root / "noun-sentiment.jsonl")
    report = {
        "schema_version": manifest.get("schema_version"),
        "status": "NORMALIZED",
        "predicate": predicate,
        "noun": noun,
        "semantic_policy": manifest.get("semantic_policy"),
        "definition_fabricated": False,
        "llm_api_used": False,
        "web_scraping_used": False,
    }
    lock = {
        "sources": [
            {
                "source_id": predicate["source_id"],
                "source_sha256": predicate["source_sha256"],
                "source_bytes": predicate["source_bytes"],
                "normalized_sha256": predicate["normalized_sha256"],
                "source_records": predicate["nonempty_source_lines"],
            },
            {
                "source_id": noun["source_id"],
                "source_sha256": noun["source_sha256"],
                "source_bytes": noun["source_bytes"],
                "normalized_sha256": noun["normalized_sha256"],
                "source_records": noun["nonempty_source_rows"],
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
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--predicate-source", type=Path, required=True)
    parser.add_argument("--noun-source", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    args = parser.parse_args()
    result = normalize_all(
        args.manifest,
        args.predicate_source,
        args.noun_source,
        args.output_root,
        args.report,
        args.lock,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
