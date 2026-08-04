from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = ROOT / "tools"
for item in (ROOT / "src", TOOLS_ROOT):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from deterministic_japanese_parser_mcp.canonical import Canonicalizer
from dictionary_supply.importers.jmdict import import_dump
import build_open_lexicon
import open_lexicon_accuracy

FIXTURE = ROOT / "tests/fixtures/dictionary_supply/jmdict-restrictions.xml"


def test_exact_only_lexicon_does_not_pollute_sentence_substrings():
    canonicalizer = Canonicalizer({
        "groups": {
            "公": ["公"],
            "公園": ["公園", "公苑"],
            "確認": ["確認"],
        },
        "exact_only_groups": ["公", "公園", "確認"],
    })
    assert canonicalizer.exact_ids("公園") == frozenset({"公園"})
    assert canonicalizer.ids("公園") == frozenset({"公園"})
    assert canonicalizer.ids("公園を確認する。") == frozenset()
    assert canonicalizer.related("公", "公園") is False
    assert canonicalizer.related("公苑", "公園") is True


def test_project_authored_synonyms_still_support_phrase_scanning():
    canonicalizer = Canonicalizer({
        "groups": {
            "README": ["README", "リードミー"],
            "公園": ["公園"],
        },
        "exact_only_groups": ["公園"],
    })
    assert canonicalizer.ids("READMEを更新する") == frozenset({"README"})
    assert canonicalizer.related("リードミー", "READMEを更新する") is True
    assert canonicalizer.ids("公園を更新する") == frozenset()


def test_accuracy_audit_checks_source_fidelity_and_lookup_precision(tmp_path):
    imported = import_dump(
        FIXTURE,
        source_version="fixture-1",
        lexical_only=True,
    )
    records = build_open_lexicon.deduplicate(imported)
    lexicon_root = tmp_path / "dictionaries/system/lexicon.d"
    shards, _ = build_open_lexicon.write_shards(
        lexicon_root,
        batch_id="fixture-accuracy",
        records=records,
        shard_size=100,
        repo_root=tmp_path,
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({
            "record_count": len(records),
            "reading_alias_promotion": False,
            "shards": shards,
        }),
        encoding="utf-8",
    )
    report, errors = open_lexicon_accuracy.audit(
        source=FIXTURE,
        lexicon_root=lexicon_root,
        manifest_path=manifest,
        minimum_records=1,
        containment_limit=100,
        pollution_limit=100,
    )
    assert errors == []
    assert report["status"] == "PASS"
    assert report["source_fidelity_records"] == 1
    assert report["exact_surface_checks"] == 2
    assert report["substring_pollution_passed"] == 2
