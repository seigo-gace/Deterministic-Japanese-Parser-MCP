from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from unified_semantic_data.source_adapter_contract import (  # noqa: E402
    compile_adapter_contract,
)


def _source(dataset: str) -> dict:
    return {
        "dataset": dataset,
        "version": "1",
        "license": "CC BY 4.0",
        "source_id": dataset,
        "source_url": "https://example.invalid",
        "source_sha256": hashlib.sha256(dataset.encode()).hexdigest(),
        "attribution": dataset,
    }


def test_adapter_contract_routes_definition_to_reference_and_new_word_candidate(
    tmp_path: Path,
) -> None:
    source = tmp_path / "adapter.jsonl"
    rows = [
        {
            "adapter_record_id": "DEF-1",
            "source_role": "lexical-definition",
            "surface": "銀行",
            "readings": ["ぎんこう"],
            "part_of_speech": "名詞",
            "meaning": "預金や融資などを扱う金融機関",
            "source": _source("meaning-source"),
        },
        {
            "adapter_record_id": "TRANS-1",
            "source_role": "translation",
            "surface": "銀行",
            "readings": ["ぎんこう"],
            "part_of_speech": "名詞",
            "payload": {"language": "en", "value": "bank"},
            "source": _source("translation-source"),
        },
    ]
    source.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    output = tmp_path / "out"
    manifest = compile_adapter_contract([source], output)
    assert manifest["adapter_record_count"] == 2
    assert manifest["semantic_reference_record_count"] == 1
    assert manifest["lexical_candidate_record_count"] == 1
    assert manifest["canonical_evidence_record_count"] == 1
    assert manifest["boundaries"]["definition_sources_create_new_word_candidates"] is True
    assert manifest["boundaries"]["new_word_candidates_require_decision_ledger_review"] is True

    semantic = [
        json.loads(line)
        for line in (output / "semantic-reference.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    lexical = [
        json.loads(line)
        for line in (output / "lexical-candidates.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    evidence = [
        json.loads(line)
        for line in (output / "canonical-evidence.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    assert semantic[0]["meanings"] == ["預金や融資などを扱う金融機関"]
    assert semantic[0]["meaning_origin"] == "source-authored"
    assert lexical[0]["record_id"] == "ADAPTER-DEF-1"
    assert lexical[0]["source_kind"] == "open_lexicon"
    assert lexical[0]["meaning_candidates"][0]["glosses"] == [
        "預金や融資などを扱う金融機関"
    ]
    assert lexical[0]["meaning_candidates"][0]["review_status"] == "needs-evidence"
    assert lexical[0]["approval_scopes"]["semantic"] == "needs-evidence"
    assert lexical[0]["automatic_approval"] is False
    assert lexical[0]["automatic_runtime_promotion"] is False
    assert evidence[0]["source_role"] == "translation"
    assert evidence[0]["payload"]["value"] == "bank"
    assert evidence[0]["automatic_meaning_generation"] is False


def test_auxiliary_role_cannot_smuggle_definition_into_meaning_pipeline(tmp_path: Path) -> None:
    source = tmp_path / "bad.jsonl"
    row = {
        "adapter_record_id": "BAD-1",
        "source_role": "sentiment",
        "surface": "最高",
        "meaning": "意味を勝手に混ぜる",
        "payload": {"polarity": "positive"},
        "source": _source("sentiment-source"),
    }
    source.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        compile_adapter_contract([source], tmp_path / "out")
    except ValueError as exc:
        assert "must not supply meanings" in str(exc)
    else:
        raise AssertionError("auxiliary source must not become a definition")


def test_definition_role_requires_real_source_authored_meaning(tmp_path: Path) -> None:
    source = tmp_path / "bad.jsonl"
    row = {
        "adapter_record_id": "BAD-DEF",
        "source_role": "lexical-definition",
        "surface": "未知語",
        "source": _source("definition-source"),
    }
    source.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        compile_adapter_contract([source], tmp_path / "out")
    except ValueError as exc:
        assert "source-authored meaning" in str(exc)
    else:
        raise AssertionError("definition role must require a meaning")
