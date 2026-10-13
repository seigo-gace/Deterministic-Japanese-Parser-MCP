"""Regression tests for explicit, evidence-bound J-Ono lexical POS decisions."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools.unified_semantic_data.review import apply_decisions, load_decisions


def _record(*, count: int = 1, jono: bool = True) -> dict:
    return {
        "record_id": "ADAPTER-FROZEN-j-ono-test",
        "input_sha256": "a" * 64,
        "part_of_speech": ["名詞:普通名詞:一般"],
        "meaning_candidates": [
            {
                "candidate_id": f"source-sense:{i}",
                "glosses": ["ahem"],
                "part_of_speech": ["名詞:普通名詞:一般"],
                "review_status": "approved",
                "evidence_ids": ["source:j-ono:ohon"],
            }
            for i in range(count)
        ],
        "review_evidence": {
            "kind": (
                "j-ono-source-authored-review-evidence"
                if jono else "unrelated-review-evidence"
            ),
        },
        "approval": {
            "blockers_by_scope": {
                "lexical": ["source-part-of-speech-required"],
                "semantic": [],
            },
            "scopes": {"lexical": "needs-evidence", "semantic": "approved"},
        },
    }


def _decision(*, status: str = "approved", scope: str = "lexical", patch=None) -> dict:
    return {
        "decision_id": "GPTCHAT-JONO-OHON-LEX",
        "record_id": "ADAPTER-FROZEN-j-ono-test",
        "scope": scope,
        "status": status,
        "reviewer": "gpt-chat-explicit-source-sense-review",
        "decided_at": "2026-10-13T09:00:00Z",
        "rationale": "J-Ono source meaning for ohon and independent JMdict ahem "
        "sense corroborate interjection POS; source identity and context reviewed.",
        "input_sha256": "a" * 64,
        "_path": "test-ledger.jsonl",
        "_line": 1,
        "patch": {"part_of_speech": ["interjection (kandoushi)"]}
        if patch is None else patch,
    }


def test_explicit_single_sense_lexical_pos_patch_updates_identity_and_candidate() -> None:
    source = _record()
    original = copy.deepcopy(source["meaning_candidates"][0])
    results, audit = apply_decisions([source], [_decision()])
    updated = results[0]
    assert updated["part_of_speech"] == ["interjection (kandoushi)"]
    assert updated["meaning_candidates"][0]["part_of_speech"] == [
        "interjection (kandoushi)"
    ]
    for field in ("candidate_id", "glosses", "evidence_ids", "review_status"):
        assert updated["meaning_candidates"][0][field] == original[field]
    assert updated["approval"]["blockers_by_scope"]["lexical"] == []
    assert "lexical" in updated["approval"]["approved_scopes"]
    assert updated["runtime_eligible"] is True
    assert audit[0]["status"] == "approved"


@pytest.mark.parametrize("decision", [
    _decision(scope="semantic"),
    _decision(status="needs-evidence"),
    _decision(patch={"part_of_speech": []}),
    _decision(patch={"part_of_speech": [""]}),
    _decision(patch={"part_of_speech": ["noun", "noun"]}),
    _decision(patch={"part_of_speech": "noun"}),
])
def test_reject_unauthorized_or_invalid_pos_patch(decision: dict) -> None:
    with pytest.raises(ValueError, match="invalid explicit lexical POS decision"):
        apply_decisions([_record()], [decision])


def test_fail_closed_without_jono_review_evidence() -> None:
    with pytest.raises(ValueError, match="requires J-Ono evidence"):
        apply_decisions([_record(jono=False)], [_decision()])


def test_fail_closed_on_multiple_source_senses() -> None:
    with pytest.raises(ValueError, match="requires one source sense"):
        apply_decisions([_record(count=2)], [_decision()])


def test_lexical_status_approved_without_explicit_pos_cannot_clear_blocker() -> None:
    with pytest.raises(ValueError, match="cannot approve blocked scope"):
        apply_decisions([_record()], [_decision(patch={})])


def test_stale_ledger_input_remains_rejected() -> None:
    decision = _decision()
    decision["input_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="stale decision input digest"):
        apply_decisions([_record()], [decision])


def test_load_decisions_checks_pos_patch_contract(tmp_path: Path) -> None:
    file = tmp_path / "ledger.jsonl"
    file.write_text(json.dumps(_decision()) + "\n", encoding="utf-8")
    assert len(load_decisions(file)) == 1
    bad = _decision(scope="semantic")
    file.write_text(json.dumps(bad) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid explicit lexical POS decision"):
        load_decisions(file)
