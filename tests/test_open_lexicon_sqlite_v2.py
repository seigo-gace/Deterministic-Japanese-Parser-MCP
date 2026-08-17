from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from deterministic_japanese_parser_mcp.open_lexicon_runtime import OpenLexiconRuntime


def _build_v2_fixture(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(root / "lexicon.sqlite3")
    db.executescript(
        """
        CREATE TABLE records(
            seq INTEGER PRIMARY KEY,
            record_id TEXT NOT NULL,
            lemma TEXT NOT NULL,
            reading TEXT NOT NULL,
            pos_json BLOB NOT NULL,
            domains_json BLOB NOT NULL,
            source_dataset TEXT NOT NULL,
            source_version TEXT NOT NULL,
            source_license TEXT NOT NULL
        );
        CREATE TABLE surface_lookup(surface TEXT NOT NULL, record_seq INTEGER NOT NULL);
        CREATE TABLE reading_lookup(reading TEXT NOT NULL, record_seq INTEGER NOT NULL);
        CREATE UNIQUE INDEX records_record_id ON records(record_id);
        CREATE INDEX surface_lookup_surface ON surface_lookup(surface, record_seq);
        CREATE INDEX reading_lookup_reading ON reading_lookup(reading, record_seq);
        """
    )
    db.execute(
        "INSERT INTO records VALUES (1,?,?,?,?,?,?,?,?)",
        (
            "D-1",
            "蛍石",
            "ホタルイシ",
            json.dumps(["名詞-普通名詞-一般"], ensure_ascii=False).encode(),
            json.dumps(["mineral"], ensure_ascii=False).encode(),
            "fixture",
            "2026-08-18",
            "R",
        ),
    )
    db.execute("INSERT INTO surface_lookup VALUES (?,?)", ("蛍石", 1))
    db.execute("INSERT INTO reading_lookup VALUES (?,?)", ("ホタルイシ", 1))
    db.commit()
    db.close()
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.2.0",
                "lookup_backend": "sqlite-index-v2",
                "record_count": 1,
                "source_versions": ["2026-08-18"],
                "exact_lookup_only": True,
                "reading_alias_promotion": False,
                "semantic_auto_promotion": False,
                "intent_auto_promotion": False,
                "external_action_auto_promotion": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_sqlite_v2_exact_and_reading_lookup(tmp_path: Path) -> None:
    root = tmp_path / "open_lexicon"
    _build_v2_fixture(root)
    runtime = OpenLexiconRuntime(root)
    assert runtime.available
    assert runtime.lookup_backend == "sqlite-index-v2"
    assert runtime.record_count == 1

    candidates, total = runtime.exact_lookup("蛍石")
    assert total == 1
    assert candidates[0].record_id == "D-1"
    assert candidates[0].lemma == "蛍石"

    candidates, total = runtime.reading_lookup(
        "ホタルイシ", surface="蛍石", normalized="蛍石"
    )
    assert total == 1
    assert candidates[0].record_id == "D-1"

    runtime.preload_records()
    assert runtime.records_preloaded
