#!/usr/bin/env python3
"""Extract the verified J-Ono source-authored adapter records for review preparation.

This tool is intentionally review-only. It never approves records and never promotes
anything into Direct Final or runtime storage.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import zipfile

SOURCE_ID = "j-ono-definitions"
EXPECTED_RECORDS = 837
FACTORY_MEMBER = "meaning-factory/source-adapter-records.jsonl"


def _source_id(row: dict) -> str:
    source = row.get("source") if isinstance(row.get("source"), dict) else {}
    return str(source.get("logical_source_id") or source.get("dataset") or "").strip()


def extract_j_ono_records(factory_zip: Path, output: Path) -> dict:
    factory_zip = Path(factory_zip)
    output = Path(output)
    with zipfile.ZipFile(factory_zip) as archive:
        names = set(archive.namelist())
        if FACTORY_MEMBER not in names:
            raise ValueError(f"missing factory member: {FACTORY_MEMBER}")
        rows: list[dict] = []
        seen: set[str] = set()
        with archive.open(FACTORY_MEMBER) as raw:
            for line_number, payload in enumerate(raw, 1):
                if not payload.strip():
                    continue
                row = json.loads(payload.decode("utf-8"))
                if not isinstance(row, dict):
                    raise ValueError(f"factory row must be object: {line_number}")
                if _source_id(row) != SOURCE_ID:
                    continue
                rid = str(row.get("adapter_record_id") or "").strip()
                if not rid:
                    raise ValueError(f"adapter_record_id missing: {line_number}")
                if rid in seen:
                    raise ValueError(f"duplicate J-Ono adapter_record_id: {rid}")
                source = row.get("source") if isinstance(row.get("source"), dict) else {}
                if source.get("public_runtime_eligible") is not True:
                    raise ValueError(f"J-Ono record is not public runtime eligible: {rid}")
                if str(row.get("source_role") or "") != "lexical-definition":
                    raise ValueError(f"J-Ono source role mismatch: {rid}")
                seen.add(rid)
                rows.append(row)

    rows.sort(key=lambda row: str(row["adapter_record_id"]))
    if len(rows) != EXPECTED_RECORDS:
        raise ValueError(
            f"J-Ono adapter record count mismatch: expected={EXPECTED_RECORDS} actual={len(rows)}"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")

    report = {
        "status": "J_ONO_REVIEW_INPUT_READY",
        "source_id": SOURCE_ID,
        "record_count": len(rows),
        "automatic_approval": False,
        "runtime_promotion": False,
        "output": str(output),
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--factory-zip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(extract_j_ono_records(args.factory_zip, args.output), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
