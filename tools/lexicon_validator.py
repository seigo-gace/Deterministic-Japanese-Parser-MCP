#!/usr/bin/env python3
"""Validate approved runtime lexicon packs and source/license evidence."""
from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = ROOT / "tools"
for item in (ROOT / "src", TOOLS_ROOT):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from dictionary_supply.common import LexiconRecord

LEXICON_DIR = ROOT / "dictionaries/system/lexicon.d"
ALLOWED_PUBLIC_LICENSES = {
    "CC0-1.0",
    "Apache-2.0",
    "CC-BY-SA-4.0",
    "CC-BY-SA-4.0 AND GFDL-1.3-or-later",
    "GPL-2.0-only OR LGPL-2.1-only OR BSD-3-Clause",
}


def main() -> int:
    errors: list[str] = []
    ids: dict[str, str] = {}
    licenses: Counter[str] = Counter()
    surfaces: dict[str, set[str]] = defaultdict(set)
    record_count = 0

    for path in sorted(LEXICON_DIR.rglob("*.jsonl")):
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                    record = LexiconRecord.from_dict(value)
                except Exception as exc:
                    errors.append(f"{path}:{line_number}: {exc}")
                    continue
                record_count += 1
                if record.review_status != "approved":
                    errors.append(
                        f"unapproved runtime record: {record.record_id}: {record.review_status}"
                    )
                if record.record_id in ids:
                    errors.append(
                        f"duplicate runtime record_id: {record.record_id}: {ids[record.record_id]} / {path}"
                    )
                ids[record.record_id] = str(path)
                license_value = record.source.license
                licenses[license_value] += 1
                if license_value not in ALLOWED_PUBLIC_LICENSES:
                    errors.append(
                        f"unapproved public license: {record.record_id}: {license_value}"
                    )
                if not record.source.source_id:
                    errors.append(f"missing source_id: {record.record_id}")
                if not record.source.source_sha256:
                    errors.append(f"missing source_sha256: {record.record_id}")
                if "private" in str(path).lower() or "PRIVATE" in license_value:
                    errors.append(f"private data in runtime pack: {record.record_id}")
                for surface in [record.lemma, *record.surfaces, *record.synonyms]:
                    if surface:
                        surfaces[surface].add(record.record_id)

    ambiguity_count = sum(
        1 for owners in surfaces.values() if len(owners) > 1
    )
    if errors:
        print("LEXICON VALIDATION FAILED")
        for error in errors:
            print("-", error)
        return 1
    print(
        "LEXICON VALIDATION OK: "
        f"records={record_count} licenses={dict(sorted(licenses.items()))} "
        f"ambiguous_surfaces={ambiguity_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
