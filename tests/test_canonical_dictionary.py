from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from unified_semantic_data.canonical_dictionary import (  # noqa: E402
    build_canonical_dictionary_records,
    compile_canonical_dictionary,
)


def _source(dataset: str, source_id: str, digest: str) -> dict:
    return {
        "dataset": dataset,
        "version": "1.0.0",
        "license": "CC-BY-4.0",
        "source_id": source_id,
        "source_url": f"https://example.invalid/{dataset}",
        "source_sha256": digest,
        "attribution": dataset,
    }


def _record(
    record_id: str,
    *,
    dataset: str,
    gloss: str,
    reading: str = "こころ",
    part_of_speech: str = "名詞",
    semantic_status: str = "approved",
) -> dict:
    source_digest = hashlib.sha256(dataset.encode("utf-8")).hexdigest()
    return {
        "record_id": record_id,
        "input_sha256": hashlib.sha256(record_id.encode("utf-8")).hexdigest(),
        "lemma": "心",
        "surfaces": ["心", "こころ"],
        "normalized_surfaces": ["心", "こころ"],
        "readings": [reading],
        "part_of_speech": [part_of_speech],
        "morphology": {
            "backend": "fixture",
            "forms": [
                {
                    "surface": "心",
                    "normalized": "心",
                    "lemma": "心",
                    "reading": reading,
                    "part_of_speech": part_of_speech,
                }
            ],
            "conjugation": {},
        },
        "domains": ["general"],
        "usage_labels": [],
        "feature_type": "",
        "meaning_candidates": [
            {
                "candidate_id": f"{record_id}:sense:001",
                "label": gloss,
                "glosses": [gloss],
                "part_of_speech": [part_of_speech],
                "domains": ["general"],
                "review_status": semantic_status,
                "register": {},
                "context": {},
            }
        ],
        "polarity": "neutral",
        "intensity": 0.0,
        "semantic_targets": ["lexicon"],
        "register": {},
        "context_conditions": {
            "required_any": [],
            "required_all": [],
            "forbidden_any": [],
            "required_social": [],
            "required_discourse": [],
        },
        "examples": {
            "positive": [f"{gloss}の用例"],
            "negative": [],
            "boundary": [],
        },
        "source": _source(dataset, record_id, source_digest),
        "approval": {
            "approved_scopes": [
                "lexical",
                "semantic",
                "pragmatic",
                "task",
                "external_action",
            ]
            if semantic_status == "approved"
            else ["lexical", "pragmatic", "task", "external_action"],
            "scopes": {
                "lexical": "approved",
                "semantic": semantic_status,
                "pragmatic": "approved",
                "task": "approved",
                "external_action": "approved",
            },
        },
        "runtime_eligible": True,
    }


def _write_review_root(path: Path, records: list[dict]) -> None:
    path.mkdir()
    (path / "approved-records.jsonl").write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
    (path / "manifest.json").write_text(
        json.dumps({"fixture": True}, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_same_lexeme_from_multiple_sources_becomes_one_project_dictionary_record(
    tmp_path: Path,
) -> None:
    review = tmp_path / "review"
    _write_review_root(
        review,
        [
            _record(
                "JMD-001",
                dataset="jmdict",
                gloss="人の感情・意志・知性などの働き",
            ),
            _record(
                "WN-001",
                dataset="wordnet-ja",
                gloss="思考や感情を担う精神的な働き",
            ),
        ],
    )

    records = build_canonical_dictionary_records(review)
    assert len(records) == 1
    row = records[0]
    assert row["dictionary_id"].startswith("CDICT-")
    assert row["lemma"] == "心"
    assert row["readings"] == ["こころ"]
    assert row["part_of_speech"] == ["名詞"]
    assert len(row["senses"]) == 2
    assert len({sense["sense_id"] for sense in row["senses"]}) == 2
    assert len({tuple(sense["glosses"]) for sense in row["senses"]}) == 2
    assert row["source_record_ids"] == ["JMD-001", "WN-001"]
    assert row["source_evidence_count"] == 2
    assert {
        source["dataset"] for source in row["source_evidence"]
    } == {"jmdict", "wordnet-ja"}
    assert row["boundaries"]["runtime_external_dictionary_lookup"] is False
    assert row["boundaries"]["automatic_meaning_generation"] is False


def test_unapproved_meaning_is_not_compiled_into_project_dictionary(
    tmp_path: Path,
) -> None:
    review = tmp_path / "review"
    _write_review_root(
        review,
        [
            _record(
                "OK",
                dataset="approved",
                gloss="承認済みの意味",
            ),
            _record(
                "PENDING",
                dataset="pending",
                gloss="未承認の意味",
                semantic_status="needs-evidence",
            ),
        ],
    )
    records = build_canonical_dictionary_records(review)
    assert len(records) == 1
    assert records[0]["source_record_ids"] == ["OK"]


def test_different_reading_or_pos_stays_separate_to_preserve_ambiguity(
    tmp_path: Path,
) -> None:
    review = tmp_path / "review"
    _write_review_root(
        review,
        [
            _record(
                "A",
                dataset="a",
                gloss="意味A",
                reading="こころ",
                part_of_speech="名詞",
            ),
            _record(
                "B",
                dataset="b",
                gloss="意味B",
                reading="しん",
                part_of_speech="名詞",
            ),
        ],
    )
    records = build_canonical_dictionary_records(review)
    assert len(records) == 2
    assert len({record["dictionary_id"] for record in records}) == 2


def test_compile_writes_search_indexes_and_is_byte_deterministic(
    tmp_path: Path,
) -> None:
    review = tmp_path / "review"
    _write_review_root(
        review,
        [
            _record(
                "JMD-001",
                dataset="jmdict",
                gloss="人の感情・意志・知性などの働き",
            ),
            _record(
                "WN-001",
                dataset="wordnet-ja",
                gloss="思考や感情を担う精神的な働き",
            ),
        ],
    )
    first = tmp_path / "first"
    second = tmp_path / "second"
    manifest1 = compile_canonical_dictionary(review, first, shard_size=100)
    compile_canonical_dictionary(review, second, shard_size=100)

    assert manifest1["record_count"] == 1
    assert manifest1["sense_count"] == 2
    assert manifest1["source_evidence_count"] == 2
    assert manifest1["boundaries"]["canonical_project_dictionary_schema"] is True

    with gzip.open(
        first / "indexes/surface-index.json.gz", "rt", encoding="utf-8"
    ) as handle:
        surface_index = json.load(handle)
    dictionary_id = next(iter(surface_index["心"]))
    assert surface_index["こころ"] == [dictionary_id]

    first_files = sorted(
        path for path in first.rglob("*") if path.is_file()
    )
    second_files = sorted(
        path for path in second.rglob("*") if path.is_file()
    )
    assert [path.relative_to(first) for path in first_files] == [
        path.relative_to(second) for path in second_files
    ]
    for left, right in zip(first_files, second_files):
        assert left.read_bytes() == right.read_bytes()
