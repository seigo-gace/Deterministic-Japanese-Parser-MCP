from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_j_ono_review_preparation_workflow_is_manual_and_review_only() -> None:
    workflow = (ROOT / ".github/workflows/j-ono-review-preparation.yml").read_text(
        encoding="utf-8"
    )
    assert "workflow_dispatch:" in workflow
    assert "push:" not in workflow
    assert "pull_request:" not in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "source-authored-meaning-data-v1" in workflow
    assert "mcp-collected-raw-factory-input-v1.zip.part-*" in workflow
    assert "RAW_SHA256" in workflow
    assert "tools/build_frozen_raw_meaning_factory.py" in workflow
    assert "--adapter-input work/rebuilt/source-adapter-records.jsonl" in workflow
    assert "tools/prepare_j_ono_review_input.py" in workflow
    assert "tools/audit_j_ono_data_quality.py" in workflow
    assert "tools/build_j_ono_collision_clusters.py" in workflow
    assert "J_ONO_REVIEW_INPUT_READING_NOT_COMPLETE" in workflow
    assert "tools/unified_semantic_data/source_adapter_contract.py" in workflow
    assert "tools/unified_semantic_data_pipeline.py" in workflow
    assert "--adapter-output-root work/j-ono-adapter" in workflow
    assert "--decision-root work/empty-decisions" in workflow
    assert "J_ONO_PREMATURE_APPROVAL" in workflow
    assert "J_ONO_PREMATURE_RUNTIME_ELIGIBILITY" in workflow
    assert "J_ONO_REVIEW_NETWORK_CALL_OCCURRED" in workflow
    assert "J_ONO_REVIEW_RUNTIME_PROMOTION_ALLOWED" in workflow
    assert "Prepare evidence-bound semantic Decision Ledger" in workflow
    assert "tools/bulk_review_station.py review" in workflow
    assert "j-ono-semantic-decision-ledger.jsonl" in workflow
    assert "J_ONO_SEMANTIC_DECISION_COUNT_MISMATCH" in workflow
    assert "J_ONO_SEMANTIC_DECISION_SCOPE_MISMATCH" in workflow
    assert "J_ONO_SEMANTIC_DECISION_UNEXPECTED_PATCH" in workflow
    assert "J_ONO_SEMANTIC_DECISION_REVIEWER_MISMATCH" in workflow
    assert '"decision_applied": False' in workflow
    assert '"approved_records_written": False' in workflow
    assert '"runtime_promotion": False' in workflow
    assert "approved_records" in workflow
    assert '"approved_records": 0' in workflow
    assert '"reading_coverage_records": 837' in workflow
    assert "J_ONO_REVIEW_READING_BLOCKER_REMAINED" in workflow
    assert "J_ONO_REVIEW_SOURCE_POS_EVIDENCE_MISMATCH" in workflow
    assert '"source_part_of_speech_required_records"' in workflow
    assert '"source_part_of_speech_coverage_records"' in workflow
    assert "J_ONO_REVIEW_PREPARATION_SCOPE_MISMATCH" in workflow
    assert "J_ONO_REVIEW_PREPARATION_SCOPE_COUNT_MISMATCH" in workflow
    assert "J_ONO_REVIEW_POLARITY_OVERREQUIRED" in workflow
    assert "J_ONO_REVIEW_INTENSITY_OVERREQUIRED" in workflow
    assert "J_ONO_REVIEW_CONTEXT_OVERREQUIRED" in workflow
    assert "J_ONO_PRAGMATIC_SCOPE_NOT_APPLICABLE_BROKEN" in workflow
    assert '"semantic_review_records"' in workflow
    assert '"pragmatic_review_records"' in workflow
    assert '"scoped_blocker_counts"' in workflow
    assert '"lexical_review_records"' in workflow
    assert '"part_of_speech_required_records"' in workflow
    assert '"lexical_blocker_counts"' in workflow
    assert '"automatic_approval": False' in workflow
    assert '"runtime_promotion": False' in workflow
    assert "git push" not in workflow
    assert "git commit" not in workflow


def test_j_ono_review_preparation_workflow_requires_exact_837_records() -> None:
    workflow = (ROOT / ".github/workflows/j-ono-review-preparation.yml").read_text(
        encoding="utf-8"
    )
    assert 'EXPECTED_J_ONO_RECORDS: "837"' in workflow
    assert "expected = 837" in workflow
    assert "J_ONO_ADAPTER_COUNT_MISMATCH" in workflow
    assert "J_ONO_REVIEW_QUEUE_COUNT_MISMATCH" in workflow
    assert "J_ONO_REVIEW_ID_CONSERVATION_MISMATCH" in workflow
