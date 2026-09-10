from __future__ import annotations

import bz2
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import build_frozen_raw_role_factory as factory_ready  # noqa: E402


def _profile() -> dict[str, object]:
    return {
        "source_id": "tatoeba-jpn-transcriptions",
        "parser_family": "delimited-table",
        "encodings": ["utf-8"],
        "delimiter": "\t",
    }


def test_tatoeba_transcription_preserves_literal_quotes(tmp_path: Path) -> None:
    path = tmp_path / "jpn_transcriptions.tsv.bz2"
    row = (
        '2174813\tjpn\tHrkt\tDominika7\t'
        '"ボルシチ "と "シー"をドイツ[語|ご]でぜったい[書|か]かないで！\n'
    )
    path.write_bytes(bz2.compress(row.encode("utf-8")))

    records = list(factory_ready._iter_factory_ready_records(path, _profile()))

    assert records == [
        {
            "columns": [
                "2174813",
                "jpn",
                "Hrkt",
                "Dominika7",
                '"ボルシチ "と "シー"をドイツ[語|ご]でぜったい[書|か]かないで！',
            ]
        }
    ]


def test_tatoeba_transcription_rejects_non_five_column_rows(tmp_path: Path) -> None:
    path = tmp_path / "jpn_transcriptions.tsv.bz2"
    path.write_bytes(bz2.compress("1\tjpn\tHrkt\tbroken\n".encode("utf-8")))

    with pytest.raises(ValueError, match="TATOEBA_TRANSCRIPTION_COLUMN_COUNT"):
        list(factory_ready._iter_factory_ready_records(path, _profile()))


def test_tatoeba_transcription_merges_single_field_continuation(tmp_path: Path) -> None:
    path = tmp_path / "jpn_transcriptions.tsv.bz2"
    rows = (
        "13492206\tjpn\tHrkt\t\t[夕暮|ゆう|ぐ]れの[駅|えき]で[差|さ]し[込|こ]んでいた。[\n"
        "|][古|ふる]い[喫茶店|きっ|さ|てん]の[窓|まど]ガラス。\n"
        "13492207\tjpn\tHrkt\t\t[正門|せい|もん]のすぐ[近|ちか]く。\n"
    )
    path.write_bytes(bz2.compress(rows.encode("utf-8")))

    records = list(factory_ready._iter_factory_ready_records(path, _profile()))

    assert len(records) == 2
    assert records[0]["columns"][0] == "13492206"
    assert records[0]["columns"][4].endswith(
        "[|][古|ふる]い[喫茶店|きっ|さ|てん]の[窓|まど]ガラス。"
    )
    assert records[1]["columns"][0] == "13492207"
