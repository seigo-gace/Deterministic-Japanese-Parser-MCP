from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools.prepare_j_ono_chat_semantic_decisions import prepare_decisions


def _write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, values: list[dict]) -> None:
    path.write_text(
        "".join(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
            for value in values
        ),
        encoding="utf-8",
    )


def _record() -> dict:
    return {
        "record_id": "ADAPTER-FROZEN-j-ono-definitions-test",
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
        "review_requirements": {
            "polarity": False,
            "intensity": False,
            "part_of_speech_source_evidence": True,
        },
        "source": {
            "source_id": "j-ono-definitions:test:001",
            "source_sha256": "a" * 64,
        },
        "review_evidence": {
            "kind": "j-ono-source-authored-review-evidence",
            "automatic_semantic_interpretation": False,
            "equivalents": ["sparkle"],
            "semantic_type_code": "m",
            "semantic_type_label": "motion-movement",
            "refer": "",
            "resolved_meaning_evidence": [
                {
                    "source_record_id": "test",
                    "source_definition_index": 1,
                    "meaning": "sparkling motion",
                    "via_refer": False,
                    "equivalents": ["sparkle"],
                    "semantic_type_code": "m",
                    "semantic_type_label": "motion-movement",
                }
            ],
        },
        "meaning_candidates": [
            {
                "label": "sparkling motion",
                "glosses": ["sparkling motion"],
                "meaning_source": "source-authored-adapter-record",
            }
        ],
    }


def _fixture(tmp_path: Path) -> dict[str, Path]:
    queue = tmp_path / "review-queue.jsonl"
    _write_jsonl(queue, [_record()])

    effectiveness = tmp_path / "effectiveness.json"
    _write_json(
        effectiveness,
        {
            "semantic_evidence": {
                "distinguished_pairs": 1,
                "total_pairs": 1,
                "clusters_with_full_pair_reduction": 1,
            },
            "interpretation_boundary": {
                "automatic_merge": False,
                "automatic_meaning_judgement": False,
                "automatic_pos_fill": False,
                "automatic_approval": False,
                "runtime_promotion": False,
            },
        },
    )

    audit = tmp_path / "audit.json"
    _write_json(
        audit,
        {
            "records": 1,
            "review_queue_records": 1,
            "approved_records": 0,
            "runtime_eligible_records": 0,
        },
    )

    existing = tmp_path / "decision_ledger.jsonl"
    _write_jsonl(
        existing,
        [
            {
                "decision_id": "EXISTING-1",
                "record_id": "OTHER-1",
                "scope": "semantic",
                "status": "approved",
                "reviewer": "fixture",
                "decided_at": "2026-01-01T00:00:00Z",
                "rationale": "fixture",
                "input_sha256": "c" * 64,
            }
        ],
    )

    authorization = tmp_path / "authorization.json"
    _write_json(
        authorization,
        {
            "review_queue_sha256": hashlib.sha256(queue.read_bytes()).hexdigest(),
            "source_evidence_effectiveness_report_sha256": hashlib.sha256(
                effectiveness.read_bytes()
            ).hexdigest(),
            "review_audit_report_sha256": hashlib.sha256(audit.read_bytes()).hexdigest(),
            "expected_record_count": 1,
            "expected_meaning_candidate_count": 1,
            "expected_semantic_pair_count": 1,
            "expected_full_cluster_reduction": 1,
            "reviewed_head": "deadbeef",
            "reviewed_run_id": 1,
            "reviewer": "gpt-chat-j-ono-evidence-review",
            "decided_at": "2026-10-11T14:43:58Z",
        },
    )
    return {
        "queue": queue,
        "effectiveness": effectiveness,
        "audit": audit,
        "existing": existing,
        "authorization": authorization,
    }


def test_prepare_j_ono_semantic_decisions_is_digest_bound_and_semantic_only(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    output = tmp_path / "combined.jsonl"
    report_path = tmp_path / "report.json"

    report = prepare_decisions(
        paths["queue"],
        paths["authorization"],
        paths["effectiveness"],
        paths["audit"],
        paths["existing"],
        output,
        report_path,
    )

    rows = [
        json.loads(line)
        for line in output.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 2
    decision = rows[-1]
    assert decision["record_id"] == _record()["record_id"]
    assert decision["scope"] == "semantic"
    assert decision["status"] == "approved"
    assert "patch" not in decision
    assert "sparkling motion" in decision["rationale"]
    assert "lexical/POS remains separately evidence-blocked" in decision["rationale"]
    assert report["new_semantic_decision_count"] == 1
    assert report["lexical_approved_records"] == 0
    assert report["decision_patch_count"] == 0
    assert report["automatic_approval"] is False
    assert report["decision_application"] is False
    assert report["runtime_promotion"] is False


def test_prepare_j_ono_semantic_decisions_fails_closed_on_queue_digest_drift(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    paths["queue"].write_text(
        paths["queue"].read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="J_ONO_CHAT_REVIEW_QUEUE_DIGEST_MISMATCH"):
        prepare_decisions(
            paths["queue"],
            paths["authorization"],
            paths["effectiveness"],
            paths["audit"],
            paths["existing"],
            tmp_path / "combined.jsonl",
            tmp_path / "report.json",
        )


def test_prepare_j_ono_semantic_decisions_rejects_untraceable_meaning(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    record = _record()
    record["meaning_candidates"][0]["label"] = "invented meaning"
    record["meaning_candidates"][0]["glosses"] = ["invented meaning"]
    _write_jsonl(paths["queue"], [record])

    authorization = json.loads(
        paths["authorization"].read_text(encoding="utf-8")
    )
    authorization["review_queue_sha256"] = hashlib.sha256(
        paths["queue"].read_bytes()
    ).hexdigest()
    _write_json(paths["authorization"], authorization)

    with pytest.raises(ValueError, match="J_ONO_CHAT_REVIEW_CANDIDATE_NOT_TRACEABLE"):
        prepare_decisions(
            paths["queue"],
            paths["authorization"],
            paths["effectiveness"],
            paths["audit"],
            paths["existing"],
            tmp_path / "combined.jsonl",
            tmp_path / "report.json",
        )
