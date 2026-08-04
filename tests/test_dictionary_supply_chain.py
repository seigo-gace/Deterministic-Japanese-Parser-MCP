from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dictionary_supply.common import LexiconRecord, read_jsonl, write_jsonl
from dictionary_supply.importers.jmdict import import_dump as import_jmdict
from dictionary_supply.importers.sudachi_csv import import_csv as import_sudachi
from dictionary_supply.importers.wikidata_lexemes import import_dump as import_wikidata
from dictionary_supply.importers.wiktionary import import_dump as import_wiktionary
from dictionary_supply.proposals import build_proposals, load_bundle, write_bundle
import promoter
import reviewer

FIXTURES = ROOT / "tests/fixtures/dictionary_supply"


def test_wiktionary_importer_extracts_japanese_dictionary_content(tmp_path):
    records = import_wiktionary(
        FIXTURES / "wiktionary.xml",
        source_version="fixture-1",
    )
    assert len(records) == 1
    record = records[0]
    assert record.lemma == "火消し"
    assert "noun" in record.part_of_speech
    assert {item["gloss"] for item in record.senses} == {
        "火事を消すこと。",
        "発生した問題や混乱を収束させること。",
    }
    assert record.synonyms == ["鎮火"]
    assert record.related == ["消火"]
    assert record.source.license.startswith("CC-BY-SA")
    assert record.source.source_sha256


def test_wikidata_importer_filters_japanese_and_preserves_forms():
    records = import_wikidata(
        FIXTURES / "wikidata-lexemes.json",
        source_version="fixture-1",
    )
    assert len(records) == 1
    record = records[0]
    assert record.lemma == "直す"
    assert record.lexical_category == "Q24905"
    assert record.forms[0]["representation"] == "直した"
    assert record.senses[0]["gloss"] == "問題のある状態を正常にする"
    assert record.source.license == "CC0-1.0"
    assert record.source.source_sha256


def test_jmdict_importer_preserves_pos_domain_and_cross_references():
    records = import_jmdict(
        FIXTURES / "jmdict.xml",
        source_version="fixture-1",
    )
    assert len(records) == 1
    record = records[0]
    assert record.lemma == "修正"
    assert record.readings == ["しゅうせい"]
    assert record.reading_mappings == [{
        "reading": "しゅうせい",
        "restricted_to": [],
        "no_kanji": False,
    }]
    assert record.surfaces == ["修正"]
    assert "computing" in record.domains
    assert "変更" in record.related
    assert "放置" in record.antonyms
    assert {item["gloss"] for item in record.senses} == {
        "correction",
        "modification",
    }


def test_jmdict_entry_is_one_record_and_preserves_reading_restrictions():
    records = import_jmdict(
        FIXTURES / "jmdict-restrictions.xml",
        source_version="fixture-1",
        lexical_only=True,
    )
    assert len(records) == 1
    record = records[0]
    assert record.source.source_id == "2000000"
    assert record.lemma == "開く"
    assert record.surfaces == ["開く", "空く"]
    assert record.readings == ["ひらく", "あく", "あき"]
    assert record.reading_mappings == [
        {
            "reading": "ひらく",
            "restricted_to": ["開く"],
            "no_kanji": False,
        },
        {
            "reading": "あく",
            "restricted_to": ["空く"],
            "no_kanji": False,
        },
        {
            "reading": "あき",
            "restricted_to": [],
            "no_kanji": True,
        },
    ]
    assert set(record.readings).isdisjoint(record.surfaces)
    assert record.senses == []


def test_sudachi_importer_preserves_reading_pos_and_normalized_form():
    records = import_sudachi(
        FIXTURES / "sudachi.csv",
        source_version="fixture-1",
    )
    assert len(records) == 2
    assert records[0].lemma == "書き換え"
    assert records[0].readings == ["カキカエ"]
    assert records[1].part_of_speech[0] == "動詞"
    assert records[1].source.license == "Apache-2.0"


def test_jsonl_schema_round_trip(tmp_path):
    records = import_wikidata(
        FIXTURES / "wikidata-lexemes.json",
        source_version="fixture-1",
    )
    path = tmp_path / "lexicon.jsonl"
    assert write_jsonl(path, records) == 1
    loaded = list(read_jsonl(path))
    assert loaded[0].to_dict() == records[0].to_dict()


def test_proposals_are_review_only_and_source_traceable(tmp_path):
    records = import_wikidata(
        FIXTURES / "wikidata-lexemes.json",
        source_version="fixture-1",
    )
    proposals = build_proposals(records)
    assert proposals
    assert all(item.status == "needs_review" for item in proposals)
    assert all(item.evidence[0]["license"] == "CC0-1.0" for item in proposals)
    output = tmp_path / "bundle.yaml"
    write_bundle(
        output,
        batch_id="fixture-batch",
        proposals=proposals,
        input_files=[FIXTURES / "wikidata-lexemes.json"],
    )
    loaded = load_bundle(output)
    assert loaded["counts"]["lexicon"] == 1


def test_reviewer_requires_conflict_resolution_and_examples(tmp_path):
    record = import_wiktionary(
        FIXTURES / "wiktionary.xml",
        source_version="fixture-1",
    )[0]
    proposals = build_proposals(
        [record],
        existing_synonym_surfaces={"鎮火"},
    )
    synonym = next(item for item in proposals if item.kind == "synonym")
    proposal = synonym.to_dict()
    decision = {
        "proposal_id": proposal["proposal_id"],
        "status": "approved",
        "notes": ["reviewed"],
    }
    try:
        reviewer.validate_approval(proposal, decision)
    except ValueError as exc:
        assert "conflict_resolution" in str(exc)
    else:
        raise AssertionError("conflicted synonym must not be approved silently")


def test_promoter_separates_licenses_and_marks_lexicon_approved(tmp_path):
    cc0 = import_wikidata(
        FIXTURES / "wikidata-lexemes.json",
        source_version="fixture-1",
    )[0]
    apache = import_sudachi(
        FIXTURES / "sudachi.csv",
        source_version="fixture-1",
        limit=1,
    )[0]
    proposals = []
    for record in (cc0, apache):
        proposal = next(
            item for item in build_proposals([record]) if item.kind == "lexicon"
        ).to_dict()
        proposal["status"] = "approved"
        proposal["review"] = {"notes": ["approved fixture record"]}
        proposals.append(proposal)
    files = promoter.prepare_files(tmp_path, "fixture-batch", proposals)
    relative = {str(path.relative_to(tmp_path)) for path in files}
    assert "dictionaries/system/lexicon.d/cc0/fixture-batch.jsonl" in relative
    assert "dictionaries/system/lexicon.d/apache-2.0/fixture-batch.jsonl" in relative
    for path, content in files.items():
        if path.suffix == ".jsonl":
            row = json.loads(content.strip())
            assert row["review_status"] == "approved"
            assert row["source"]["license"] in {"CC0-1.0", "Apache-2.0"}


def private_record() -> LexiconRecord:
    return LexiconRecord.from_dict({
        "schema_version": "1.0.0",
        "record_id": "PRIVATE-1",
        "lemma": "APIを公開",
        "source": {
            "dataset": "private-log",
            "version": "1",
            "license": "PRIVATE-REVIEW-ONLY",
            "source_id": "1",
        },
        "review_status": "needs_review",
    })


def test_private_log_lexicon_cannot_be_promoted(tmp_path):
    proposal = next(
        item
        for item in build_proposals([private_record()])
        if item.kind == "lexicon"
    ).to_dict()
    proposal["status"] = "approved"
    proposal["review"] = {"notes": ["must remain private"]}
    try:
        promoter.prepare_files(tmp_path, "private-batch", [proposal])
    except ValueError as exc:
        assert "cannot be promoted" in str(exc)
    else:
        raise AssertionError("private log content must never enter public packs")


def test_private_log_rule_cannot_be_promoted(tmp_path):
    proposal = next(
        item
        for item in build_proposals([private_record()])
        if item.kind == "rule"
    ).to_dict()
    proposal["status"] = "approved"
    proposal["review"] = {
        "notes": ["must remain private"],
        "positive_examples": ["APIを公開しろ。"],
        "negative_examples": ["APIを公開しない。"],
        "external_action_reviewed": True,
    }
    try:
        promoter.prepare_files(tmp_path, "private-rule-batch", [proposal])
    except ValueError as exc:
        assert "cannot be promoted" in str(exc)
    else:
        raise AssertionError(
            "private log evidence must never enter public rule packs"
        )
