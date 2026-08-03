from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys

TOOLS_ROOT = Path(__file__).resolve().parents[2]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dictionary_supply.common import (
    LexiconRecord,
    SourceInfo,
    normalize_text,
    open_text,
    sha256_file,
    stable_id,
    write_jsonl,
)


def parse_row(
    row: list[str],
    *,
    source_version: str,
    source_sha256: str,
    row_number: int,
) -> LexiconRecord | None:
    # Sudachi source CSV layout:
    # left_id,right_id,cost,surface,pos1..pos6,reading,normalized_form,
    # dictionary_form_word_id,split_type,a_unit_split,b_unit_split,word_structure
    if len(row) < 12:
        return None
    surface = normalize_text(row[3])
    if not surface or surface == "*":
        return None
    pos = [normalize_text(item) for item in row[4:10] if normalize_text(item) not in {"", "*"}]
    reading = normalize_text(row[10]) if len(row) > 10 else ""
    normalized = normalize_text(row[11]) if len(row) > 11 else surface
    lemma = normalized if normalized and normalized != "*" else surface
    source = SourceInfo(
        dataset="SudachiDict",
        version=source_version,
        license="Apache-2.0",
        source_id=f"row:{row_number}",
        source_url="https://github.com/WorksApplications/SudachiDict",
        source_sha256=source_sha256,
        attribution="Works Applications Co., Ltd. and contributors",
    )
    forms = []
    if surface != lemma:
        forms.append({
            "representation": surface,
            "grammatical_features": ["dictionary_surface"],
            "reading": reading or None,
        })
    return LexiconRecord(
        record_id=stable_id("SUD", lemma, reading, "/".join(pos), str(row_number)),
        lemma=lemma,
        readings=[reading] if reading and reading != "*" else [],
        surfaces=[surface, lemma],
        part_of_speech=pos,
        lexical_category=pos[0] if pos else None,
        forms=forms,
        source=source,
        review_status="needs_review",
    ).normalized()


def import_csv(
    path: Path,
    *,
    source_version: str,
    limit: int | None = None,
) -> list[LexiconRecord]:
    checksum = sha256_file(path)
    output: list[LexiconRecord] = []
    with open_text(path) as handle:
        reader = csv.reader(handle)
        for row_number, row in enumerate(reader, 1):
            record = parse_row(
                row,
                source_version=source_version,
                source_sha256=checksum,
                row_number=row_number,
            )
            if record is None:
                continue
            output.append(record)
            if limit is not None and len(output) >= limit:
                break
    return output


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import SudachiDict source CSV into JSONL."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-version", required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    count = write_jsonl(
        args.output,
        import_csv(
            args.input,
            source_version=args.source_version,
            limit=args.limit,
        ),
    )
    print(f"SUDACHI IMPORT OK: records={count} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
