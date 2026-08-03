from __future__ import annotations

import gzip
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = ROOT / "tools"
for item in (ROOT / "src", TOOLS_ROOT):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from deterministic_japanese_parser_mcp.canonical import Canonicalizer
from deterministic_japanese_parser_mcp.dictionaries import _load_lexicon_set
from dictionary_supply.common import LexiconRecord, SourceInfo, write_jsonl
import build_open_lexicon


def records(count: int) -> list[LexiconRecord]:
    return [
        LexiconRecord(
            record_id=f"JMD-{index:06d}",
            lemma=f"試験語{index:06d}",
            readings=[f"シケンゴ{index:06d}"],
            surfaces=[f"試験語{index:06d}", f"表記{index:06d}"],
            part_of_speech=["noun"],
            senses=[{
                "gloss": f"意味{index}",
                "language": "ja",
            }],
            synonyms=[f"同義語{index:06d}"],
            forms=[{
                "representation": f"活用{index:06d}",
                "grammatical_features": ["fixture"],
            }],
            source=SourceInfo(
                dataset="JMdict",
                version="fixture-1",
                license="CC-BY-SA-4.0",
                source_id=str(index),
                source_sha256="a" * 64,
                attribution=(
                    "Electronic Dictionary Research and Development Group"
                ),
            ),
            review_status="needs_review",
        )
        for index in range(count)
    ]


def test_base_builder_auto_approves_only_lexical_identity():
    record = build_open_lexicon.lexical_base_record(records(1)[0])
    assert record.review_status == "approved"
    assert record.senses == []
    assert record.synonyms == []
    assert record.antonyms == []
    assert record.related == []
    assert record.forms == []
    assert record.lemma == "試験語000000"
    assert "表記000000" in record.surfaces
    assert any("No intent" in note for note in record.notes)


def test_base_builder_writes_compressed_license_shards(tmp_path):
    output_root = tmp_path / "dictionaries/system/lexicon.d"
    selected = build_open_lexicon.deduplicate(records(25))
    shards, compressed_bytes = build_open_lexicon.write_shards(
        output_root,
        batch_id="fixture-base",
        records=selected,
        shard_size=10,
    )
    assert len(shards) == 3
    assert compressed_bytes > 0
    paths = sorted(output_root.rglob("*.jsonl.gz"))
    assert len(paths) == 3
    lines = []
    for path in paths:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            lines.extend(line for line in handle if line.strip())
    assert len(lines) == 25
    assert all(json.loads(line)["review_status"] == "approved" for line in lines)


def test_runtime_loader_reads_compressed_shards_without_record_copies(tmp_path):
    output_root = tmp_path / "lexicon.d"
    selected = build_open_lexicon.deduplicate(records(30))
    build_open_lexicon.write_shards(
        output_root,
        batch_id="fixture-runtime",
        records=selected,
        shard_size=10,
    )
    loaded = _load_lexicon_set(output_root)
    assert loaded["record_count"] == 30
    assert "entries" not in loaded
    assert loaded["groups"]["試験語000005"] == [
        "試験語000005",
        "表記000005",
    ]


def test_builder_rejects_untrusted_private_source():
    record = records(1)[0]
    record.source = SourceInfo(
        dataset="private-log",
        version="1",
        license="PRIVATE-REVIEW-ONLY",
        source_id="1",
        source_sha256="b" * 64,
    )
    try:
        build_open_lexicon.lexical_base_record(record)
    except ValueError as exc:
        assert "not trusted" in str(exc)
    else:
        raise AssertionError("private sources must not enter the lexical base")


def test_canonical_trie_handles_large_surface_sets_without_first_char_scans():
    groups = {
        f"正本{index:05d}": [
            f"正本{index:05d}",
            f"表記{index:05d}",
        ]
        for index in range(10000)
    }
    canonicalizer = Canonicalizer({"groups": groups})
    assert not hasattr(canonicalizer, "by_first")
    assert canonicalizer.ids("この表記09999を確認する") == frozenset({
        "正本09999"
    })
    assert canonicalizer.related("表記01234", "正本01234")


def test_build_minimum_contract_fails_below_target(tmp_path):
    imported = tmp_path / "small.jsonl"
    write_jsonl(imported, records(5))
    loaded = build_open_lexicon.deduplicate(
        list(build_open_lexicon.read_jsonl(imported))
    )
    assert len(loaded) == 5
    required = 10
    try:
        if len(loaded) < required:
            raise RuntimeError(
                f"open lexicon minimum was not reached: required={required} actual={len(loaded)}"
            )
    except RuntimeError as exc:
        assert "required=10 actual=5" in str(exc)
    else:
        raise AssertionError("minimum contract must fail")
