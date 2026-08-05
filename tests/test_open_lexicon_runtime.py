from __future__ import annotations

import gzip
import json
from pathlib import Path

from deterministic_japanese_parser_mcp.models import OriginalSpan, Token
from deterministic_japanese_parser_mcp.open_lexicon_runtime import OpenLexiconRuntime


def _write_json_gzip(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True)


def _write_fixture(root: Path) -> None:
    records = [
        {
            "record_id": "R1",
            "lemma": "橋",
            "surfaces": ["橋"],
            "readings": ["はし"],
            "reading_mappings": [
                {"reading": "はし", "restricted_to": ["橋"], "no_kanji": False}
            ],
            "part_of_speech": ["noun"],
            "lexical_category": None,
            "domains": ["general"],
            "usage_labels": [],
            "source": {
                "dataset": "JMdict",
                "version": "fixture",
                "license": "CC-BY-SA-4.0",
                "source_id": "1"
            },
            "review_status": "approved"
        },
        {
            "record_id": "R2",
            "lemma": "箸",
            "surfaces": ["箸"],
            "readings": ["はし"],
            "reading_mappings": [
                {"reading": "はし", "restricted_to": ["箸"], "no_kanji": False}
            ],
            "part_of_speech": ["noun"],
            "lexical_category": None,
            "domains": ["food"],
            "usage_labels": [],
            "source": {
                "dataset": "JMdict",
                "version": "fixture",
                "license": "CC-BY-SA-4.0",
                "source_id": "2"
            },
            "review_status": "approved"
        },
        {
            "record_id": "R3",
            "lemma": "生",
            "surfaces": ["生"],
            "readings": ["なま"],
            "reading_mappings": [],
            "part_of_speech": ["noun"],
            "lexical_category": None,
            "domains": [],
            "usage_labels": [],
            "source": {
                "dataset": "JMdict",
                "version": "fixture",
                "license": "CC-BY-SA-4.0",
                "source_id": "3"
            },
            "review_status": "approved"
        },
        {
            "record_id": "R4",
            "lemma": "生もの",
            "surfaces": ["生もの", "生"],
            "readings": ["なまもの"],
            "reading_mappings": [],
            "part_of_speech": ["noun"],
            "lexical_category": None,
            "domains": ["food"],
            "usage_labels": [],
            "source": {
                "dataset": "JMdict",
                "version": "fixture",
                "license": "CC-BY-SA-4.0",
                "source_id": "4"
            },
            "review_status": "approved"
        }
    ]
    record_path = root / "records/records-0000.jsonl.gz"
    record_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(record_path, "wt", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    _write_json_gzip(
        root / "indexes/surface-index.json.gz",
        {"橋": ["R1"], "箸": ["R2"], "生": ["R3", "R4"], "生もの": ["R4"]}
    )
    _write_json_gzip(
        root / "indexes/reading-index.json.gz",
        {
            "はし": [
                {"record_id": "R1", "restricted_to": ["橋"], "no_kanji": False},
                {"record_id": "R2", "restricted_to": ["箸"], "no_kanji": False}
            ],
            "なま": [
                {"record_id": "R3", "restricted_to": [], "no_kanji": False}
            ]
        }
    )
    _write_json_gzip(
        root / "indexes/record-locator.json.gz",
        {
            record["record_id"]: {"shard": 0, "line": index + 1}
            for index, record in enumerate(records)
        }
    )
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "record_count": 4,
                "source_versions": ["fixture"],
                "unique_lemmas": 4,
                "unique_surfaces": 4,
                "unique_readings": 2,
                "homograph_surfaces": 1,
                "exact_lookup_only": True,
                "reading_alias_promotion": False,
                "semantic_auto_promotion": False,
                "intent_auto_promotion": False,
                "external_action_auto_promotion": False
            },
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


def test_exact_lookup_preserves_same_surface_ambiguity(tmp_path: Path):
    root = tmp_path / "open_lexicon"
    _write_fixture(root)
    runtime = OpenLexiconRuntime(root)

    candidates, total = runtime.exact_lookup("生", max_candidates=8)

    assert runtime.available is True
    assert total == 2
    assert [item.record_id for item in candidates] == ["R3", "R4"]
    assert {item.lemma for item in candidates} == {"生", "生もの"}


def test_reading_restriction_filters_unrelated_writing(tmp_path: Path):
    root = tmp_path / "open_lexicon"
    _write_fixture(root)
    runtime = OpenLexiconRuntime(root)

    candidates, total = runtime.reading_lookup(
        "ハシ",
        surface="橋",
        normalized="橋"
    )

    assert total == 1
    assert candidates[0].record_id == "R1"
    assert candidates[0].restricted_to == ["橋"]


def test_token_annotation_exposes_candidates_without_selecting_a_sense(tmp_path: Path):
    root = tmp_path / "open_lexicon"
    _write_fixture(root)
    runtime = OpenLexiconRuntime(root)
    token = Token(
        surface="生",
        normalized="生",
        reading="ナマ",
        pos=["名詞"],
        span=OriginalSpan(start=0, end=1, source_text="生")
    )

    annotated = runtime.lookup_token(token)

    assert annotated.lexical_status == "AMBIGUOUS"
    assert annotated.lexical_candidate_total == 2
    assert [item.record_id for item in annotated.lexical_candidates] == ["R3", "R4"]
    assert all(item.match_type == "surface" for item in annotated.lexical_candidates)
