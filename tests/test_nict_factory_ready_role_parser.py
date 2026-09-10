from __future__ import annotations

import gzip
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from build_frozen_raw_role_factory import (  # noqa: E402
    _NICT_DEPENDENCY_SOURCE_ID,
    _iter_factory_ready_records,
)


def _nict_profile() -> dict:
    return {
        "source_id": _NICT_DEPENDENCY_SOURCE_ID,
        "parser_family": "delimited-table",
        "encodings": ["utf-8"],
        "delimiter": "\t",
    }


def test_nict_normalized_json_string_tsv_preserves_embedded_quotes(tmp_path: Path) -> None:
    path = tmp_path / "relations-00001.tsv.gz"
    dependent = '彼は"引用"した'
    marker = "<を>"
    head = '確認"済み"'
    row = "\t".join(
        (
            json.dumps(dependent, ensure_ascii=False, separators=(",", ":")),
            json.dumps(marker, ensure_ascii=False, separators=(",", ":")),
            json.dumps(head, ensure_ascii=False, separators=(",", ":")),
            "17",
            "1",
            "0",
        )
    )
    with gzip.open(path, "wt", encoding="utf-8", newline="\n") as handle:
        handle.write(row + "\n")

    records = list(_iter_factory_ready_records(path, _nict_profile()))

    assert records == [
        {
            "surfaces": [dependent, head],
            "dependent": dependent,
            "relation_marker": marker,
            "head": head,
            "frequency": 17,
            "dependent_meaning_exact_match": True,
            "head_meaning_exact_match": False,
            "normalized_source_format": _NICT_DEPENDENCY_SOURCE_ID,
        }
    ]


def test_nict_normalized_row_fails_closed_on_column_loss(tmp_path: Path) -> None:
    path = tmp_path / "relations-00002.tsv.gz"
    with gzip.open(path, "wt", encoding="utf-8", newline="\n") as handle:
        handle.write('"係り元"\t"<を>"\t"係り先"\t1\t1\n')

    with pytest.raises(ValueError, match="NICT_DEPENDENCY_COLUMN_COUNT"):
        list(_iter_factory_ready_records(path, _nict_profile()))


def test_non_nict_delimited_table_keeps_existing_parser(tmp_path: Path) -> None:
    path = tmp_path / "ordinary.csv"
    path.write_text("語,名詞\n", encoding="utf-8")
    profile = {
        "source_id": "ordinary-source",
        "parser_family": "delimited-table",
        "encodings": ["utf-8"],
        "delimiter": ",",
    }
    assert list(_iter_factory_ready_records(path, profile)) == [
        {"columns": ["語", "名詞"]}
    ]
