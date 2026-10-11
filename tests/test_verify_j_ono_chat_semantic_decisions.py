from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.prepare_j_ono_chat_semantic_decisions import _decision_for
from tools.verify_j_ono_chat_semantic_decisions import verify_existing_decisions


def _write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def _record(record_id: str) -> dict:
    return {
        "record_id": record_id,
        "input_sha256": "b" * 64,
        "runtime_eligible": False,
        "approval": {
            "review_scopes": ["lexical", "semantic"],
            "approved_scopes": [],
            "scopes": {
                "lexical": "needs-evidence",
                "semantic": "needs-evidence",
                "pragmatic": "not-applicable",
                "task": "not-applicable",
                "external_action": "not-applicable",
            },
            "blockers_by_scope": {
                "lexical": ["source-part-of-speech-required"],
                "semantic": [],
                "pragmatic": [],
                "task": [],
                "external_action": [],
            },
        },
        "review_requirements": {"polarity": False, "intensity": False},
        "source": {
            "source_id": "j-ono-definitions:test:001",
            "source_sha256": "a" * 64,
        },
        "review_evidence": {
            "kind": "j-ono-source-authored-review-evidence",
            "automatic_semantic_interpretation": False,
            "resolved_meaning_evidence": [
                {
                    "source_record_id": "test",
                    "source_definition_index": 1,
                    "meaning": "sparkling motion",
                    "via_refer": False,
                }
            ],
            "equivalents": ["sparkle"],
            "semantic_type_code": "m",
            "semantic_type_label": "motion-movement",
            "refer": "",
        },
        "meaning_candidates": [
            {
                "label": "sparkling motion",
                "glosses": ["sparkling motion"],
                "meaning_source": "source-authored-adapter-record",
            }
        ],
    }


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, dict]:
    queue = tmp_path / "queue.jsonl"
    record = _record("ADAPTER-FROZEN-j-ono-definitions-test")
    _write_jsonl(queue, [record])
    authorization = tmp_path / "authorization.json"
    auth = {
        "expected_record_count": 1,
        "expected_meaning_candidate_count": 1,
        "reviewer": "gpt-chat-j-ono-evidence-review",
        "decided_at": "2026-10-11T14:43:58Z",
    }
    _write_json(authorization, auth)
    ledger = tmp_path / "decision_ledger.jsonl"
    ledger.write_text("", encoding="utf-8")
    return queue, authorization, ledger, record


def test_verify_existing_j_ono_decisions_reports_not_applied(tmp_path: Path) -> None:
    queue, authorization, ledger, _record_value = _fixture(tmp_path)
    report = verify_existing_decisions(queue, authorization, ledger)
    assert report["status"] == "NOT_APPLIED"
    assert report["existing_exact_semantic_decision_count"] == 0
    assert report["new_semantic_decision_required"] is True
    assert report["automatic_approval"] is False
    assert report["decision_application"] is False
    assert report["runtime_promotion"] is False


def test_verify_existing_j_ono_decisions_accepts_exact_authorized_decision(
    tmp_path: Path,
) -> None:
    queue, authorization, ledger, record = _fixture(tmp_path)
    decision = _decision_for(
        record,
        reviewer="gpt-chat-j-ono-evidence-review",
        decided_at="2026-10-11T14:43:58Z",
    )
    _write_jsonl(ledger, [decision])

    report = verify_existing_decisions(queue, authorization, ledger)
    assert report["status"] == "ALREADY_APPLIED"
    assert report["existing_exact_semantic_decision_count"] == 1
    assert report["new_semantic_decision_required"] is False


def test_verify_existing_j_ono_decisions_fails_on_mismatch(tmp_path: Path) -> None:
    queue, authorization, ledger, record = _fixture(tmp_path)
    decision = _decision_for(
        record,
        reviewer="gpt-chat-j-ono-evidence-review",
        decided_at="2026-10-11T14:43:58Z",
    )
    decision["rationale"] = "tampered"
    _write_jsonl(ledger, [decision])

    with pytest.raises(
        ValueError,
        match="J_ONO_CHAT_EXISTING_VERIFY_DECISION_MISMATCH",
    ):
        verify_existing_decisions(queue, authorization, ledger)
