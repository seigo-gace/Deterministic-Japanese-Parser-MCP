from __future__ import annotations

import json
from pathlib import Path
import zipfile

import pytest

from tools.prepare_j_ono_review_input import (
    EXPECTED_RECORDS,
    FACTORY_MEMBER,
    extract_j_ono_records,
    extract_j_ono_records_from_jsonl,
)


def _row(index: int, *, source_id: str = "j-ono-definitions") -> dict:
    return {
        "adapter_record_id": f"FROZEN-{source_id}-{index:024d}",
        "source_role": "lexical-definition",
        "surfaces": [f"語{index}"],
        "readings": [],
        "part_of_speech_list": [],
        "domains": [],
        "meanings": [f"意味{index}"],
        "source": {
            "dataset": source_id,
            "logical_source_id": source_id,
            "public_runtime_eligible": True,
        },
        "payload": {},
    }


def _factory_zip(path: Path, rows: list[dict]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        text = "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        )
        archive.writestr(FACTORY_MEMBER, text)


def test_extract_j_ono_records_preserves_exact_837_and_excludes_other_sources(tmp_path: Path):
    source = tmp_path / "factory.zip"
    rows = [_row(i) for i in range(EXPECTED_RECORDS)]
    rows.append(_row(999999, source_id="japanese-wordnet-1.1"))
    _factory_zip(source, rows)

    output = tmp_path / "j-ono.jsonl"
    report = extract_j_ono_records(source, output)

    assert report["record_count"] == EXPECTED_RECORDS
    assert report["automatic_approval"] is False
    assert report["runtime_promotion"] is False
    extracted = [
        json.loads(line)
        for line in output.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(extracted) == EXPECTED_RECORDS
    assert {row["source"]["logical_source_id"] for row in extracted} == {"j-ono-definitions"}


def test_extract_j_ono_records_from_rebuilt_jsonl_preserves_exact_837(tmp_path: Path):
    source = tmp_path / "source-adapter-records.jsonl"
    rows = [_row(i) for i in range(EXPECTED_RECORDS)]
    rows.append(_row(999999, source_id="japanese-wordnet-1.1"))
    source.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    output = tmp_path / "j-ono.jsonl"
    report = extract_j_ono_records_from_jsonl(source, output)
    assert report["record_count"] == EXPECTED_RECORDS
    extracted = [
        json.loads(line)
        for line in output.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(extracted) == EXPECTED_RECORDS
    assert all(row["source"]["logical_source_id"] == "j-ono-definitions" for row in extracted)


def test_extract_j_ono_records_fails_closed_on_count_mismatch(tmp_path: Path):
    source = tmp_path / "factory.zip"
    _factory_zip(source, [_row(1)])
    with pytest.raises(ValueError, match="record count mismatch"):
        extract_j_ono_records(source, tmp_path / "out.jsonl")


def test_extract_j_ono_records_fails_closed_on_runtime_ineligible_record(tmp_path: Path):
    source = tmp_path / "factory.zip"
    rows = [_row(i) for i in range(EXPECTED_RECORDS)]
    rows[0]["source"]["public_runtime_eligible"] = False
    _factory_zip(source, rows)
    with pytest.raises(ValueError, match="not public runtime eligible"):
        extract_j_ono_records(source, tmp_path / "out.jsonl")
