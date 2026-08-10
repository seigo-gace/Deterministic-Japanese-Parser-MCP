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

from unified_semantic_data.canonical_dictionary import compile_canonical_dictionary  # noqa: E402
from unified_semantic_data.canonical_evidence import (  # noqa: E402
    compile_evidence_enriched_dictionary,
)


def _lexical_record(record_id: str, surface: str, reading: str, gloss: str) -> dict:
    return {
        "record_id": record_id,
        "input_sha256": hashlib.sha256(record_id.encode()).hexdigest(),
        "lemma": surface,
        "surfaces": [surface],
        "normalized_surfaces": [surface],
        "readings": [reading],
        "part_of_speech": ["名詞"],
        "morphology": {"backend": "fixture", "forms": [], "conjugation": {}},
        "domains": [],
        "usage_labels": [],
        "feature_type": "",
        "meaning_candidates": [{
            "candidate_id": f"{record_id}:sense:001",
            "label": gloss,
            "glosses": [gloss],
            "part_of_speech": ["名詞"],
            "domains": [],
            "parameters": {},
            "register": {},
            "context": {},
            "review_status": "approved",
        }],
        "polarity": "neutral",
        "intensity": 0.0,
        "semantic_targets": ["lexicon"],
        "parameters": {},
        "register": {},
        "context_conditions": {},
        "task_candidates": [],
        "examples": {"positive": [], "negative": [], "boundary": []},
        "risk_class": "semantic",
        "external_action_risk": False,
        "source": {
            "dataset": "fixture-dictionary",
            "version": "1",
            "license": "MIT",
            "source_id": record_id,
            "source_url": "https://example.invalid",
            "source_sha256": hashlib.sha256(b"fixture").hexdigest(),
            "attribution": "fixture",
        },
        "approval": {
            "scopes": {
                "lexical": "approved", "semantic": "approved",
                "pragmatic": "approved", "task": "approved",
                "external_action": "approved",
            },
            "approved_scopes": [
                "external_action", "lexical", "pragmatic", "semantic", "task"
            ],
            "review_scopes": [],
            "blockers_by_scope": {
                "lexical": [], "semantic": [], "pragmatic": [],
                "task": [], "external_action": [],
            },
        },
        "runtime_eligible": True,
    }


def _review_root(path: Path, records: list[dict]) -> Path:
    path.mkdir()
    (path / "approved-records.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records),
        encoding="utf-8",
    )
    (path / "manifest.json").write_text("{}\n", encoding="utf-8")
    return path


def _evidence(
    evidence_id: str,
    *,
    surface: str,
    reading: str | None,
    role: str,
    payload: dict,
) -> dict:
    return {
        "evidence_id": evidence_id,
        "source_role": role,
        "surface": surface,
        "readings": [reading] if reading else [],
        "part_of_speech_list": ["名詞"],
        "payload": payload,
        "source": {
            "dataset": "aux-fixture",
            "version": "1",
            "license": "CC BY 4.0",
            "source_id": evidence_id,
            "source_url": "https://example.invalid/aux",
            "source_sha256": hashlib.sha256(evidence_id.encode()).hexdigest(),
            "attribution": "aux-fixture",
        },
    }


def test_auxiliary_evidence_attaches_without_becoming_new_meaning(tmp_path: Path) -> None:
    review = _review_root(
        tmp_path / "review",
        [_lexical_record("LEX-1", "銀行", "ぎんこう", "預金や融資などを扱う金融機関")],
    )
    master = tmp_path / "master"
    compile_canonical_dictionary(review, master, shard_size=100)
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    rows = [
        _evidence(
            "FAM-1",
            surface="銀行",
            reading="ぎんこう",
            role="familiarity",
            payload={"score": 6.2, "scale": "1-7"},
        ),
        _evidence(
            "TRANS-1",
            surface="銀行",
            reading="ぎんこう",
            role="translation",
            payload={"language": "en", "value": "bank"},
        ),
    ]
    (evidence_root / "evidence.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    enriched = tmp_path / "enriched"
    manifest = compile_evidence_enriched_dictionary(
        master, [evidence_root], enriched, shard_size=100
    )
    assert manifest["record_count"] == 1
    assert manifest["sense_count"] == 1
    assert manifest["auxiliary_evidence_count"] == 2
    assert manifest["auxiliary_join_status_counts"] == {"attached": 2}
    with gzip.open(
        enriched / "records/dictionary-0000.jsonl.gz", "rt", encoding="utf-8"
    ) as handle:
        record = json.loads(next(handle))
    assert len(record["senses"]) == 1
    assert record["senses"][0]["glosses"] == ["預金や融資などを扱う金融機関"]
    assert record["auxiliary_evidence"]["familiarity"][0]["payload"]["score"] == 6.2
    assert record["auxiliary_evidence"]["translation"][0]["payload"]["value"] == "bank"


def test_ambiguous_surface_only_evidence_is_not_attached(tmp_path: Path) -> None:
    review = _review_root(
        tmp_path / "review",
        [
            _lexical_record("LEX-A", "生", "せい", "生きていることに関する語義"),
            _lexical_record("LEX-B", "生", "なま", "加熱・加工していないこと"),
        ],
    )
    master = tmp_path / "master"
    compile_canonical_dictionary(review, master, shard_size=100)
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    row = _evidence(
        "CLASS-AMB",
        surface="生",
        reading=None,
        role="semantic-class",
        payload={"class": "1.0000"},
    )
    (evidence_root / "evidence.jsonl").write_text(
        json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    enriched = tmp_path / "enriched"
    manifest = compile_evidence_enriched_dictionary(
        master, [evidence_root], enriched, shard_size=100
    )
    assert manifest["auxiliary_join_status_counts"] == {"ambiguous": 1}
    report = [
        json.loads(line)
        for line in (enriched / "auxiliary-evidence-join-report.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    assert report[0]["status"] == "ambiguous"
    assert len(report[0]["candidate_dictionary_ids"]) == 2


def test_reading_disambiguates_auxiliary_join(tmp_path: Path) -> None:
    review = _review_root(
        tmp_path / "review",
        [
            _lexical_record("LEX-A", "生", "せい", "生きていることに関する語義"),
            _lexical_record("LEX-B", "生", "なま", "加熱・加工していないこと"),
        ],
    )
    master = tmp_path / "master"
    compile_canonical_dictionary(review, master, shard_size=100)
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    row = _evidence(
        "CLASS-NAMA",
        surface="生",
        reading="なま",
        role="semantic-class",
        payload={"class": "状態"},
    )
    (evidence_root / "evidence.jsonl").write_text(
        json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    enriched = tmp_path / "enriched"
    manifest = compile_evidence_enriched_dictionary(
        master, [evidence_root], enriched, shard_size=100
    )
    assert manifest["auxiliary_join_status_counts"] == {"attached": 1}
