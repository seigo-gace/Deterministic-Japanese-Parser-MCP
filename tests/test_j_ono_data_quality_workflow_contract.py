from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_j_ono_quality_audit_runs_on_real_release_without_promotion() -> None:
    workflow = (ROOT / ".github/workflows/j-ono-data-quality-audit.yml").read_text(
        encoding="utf-8"
    )
    assert "pull_request:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "source-authored-meaning-data-v1" in workflow
    assert "mcp-source-authored-meaning-factory-v1.zip" in workflow
    assert "tools/prepare_j_ono_review_input.py" in workflow
    assert "tools/audit_j_ono_data_quality.py" in workflow
    assert "tools/build_j_ono_collision_clusters.py" in workflow
    assert "tools/measure_j_ono_source_evidence_effectiveness.py" in workflow
    assert "tools/public_onomatopoeia_sources.py" in workflow
    assert "tools/build_frozen_raw_meaning_factory.py" in workflow
    assert "tools/unified_semantic_data/frozen_raw_meaning_factory.py" in workflow
    assert "tools/unified_semantic_data/source_adapter_contract.py" in workflow
    assert "tools/unified_semantic_data_pipeline.py" in workflow
    assert "tools/bulk_review_station.py" in workflow
    assert "--expected-reading-unresolved 124" in workflow
    assert "J_ONO_SOURCE_EVIDENCE_TARGET_CLUSTER_COUNT_MISMATCH" in workflow
    assert "J_ONO_EXAMPLE_METADATA_SEMANTIC_OVERCLAIM" in workflow
    assert "J_ONO_MISSING_EVIDENCE_OVERCLAIM" in workflow
    assert "J_ONO_SOURCE_EVIDENCE_BOUNDARY_BROKEN" in workflow
    assert "J_ONO_REFER_TARGET_SEMANTIC_EVIDENCE_NOT_USED" in workflow
    assert "J_ONO_REVIEW_AUDIT_TOTAL_MISMATCH" in workflow
    assert "J_ONO_REVIEW_AUDIT_QUEUE_MISMATCH" in workflow
    assert "J_ONO_REVIEW_AUDIT_READING_BLOCKER_REMAINED" in workflow
    assert "J_ONO_REVIEW_AUDIT_TASK_SCOPE_NOT_APPLICABLE_BROKEN" in workflow
    assert "J_ONO_REVIEW_AUDIT_ACTION_SCOPE_NOT_APPLICABLE_BROKEN" in workflow
    assert '"approved_records": 0' in workflow
    assert '"runtime_eligible_records": 0' in workflow
    assert '"automatic_pos_fill": False' in workflow
    assert "mcp-collected-raw-factory-input-v1.zip.part-*" in workflow
    assert "tools/build_frozen_raw_meaning_factory.py" in workflow
    assert "python -m tools.unified_semantic_data.source_adapter_contract" in workflow
    assert "python tools/unified_semantic_data/source_adapter_contract.py" not in workflow
    assert "J_ONO_REAL_DATA_HARD_FAILURE" in workflow
    assert "J_ONO_CLUSTER_COUNT_MISMATCH" in workflow
    assert "J_ONO_CLUSTER_AUTO_MERGE_FORBIDDEN" in workflow
    assert "J_ONO_AUTO_MEANING_JUDGEMENT_FORBIDDEN" in workflow
    assert "J_ONO_AUTO_APPROVAL_FORBIDDEN" in workflow
    assert "J_ONO_RUNTIME_PROMOTION_FORBIDDEN" in workflow
    assert "git push" not in workflow
    assert "git commit" not in workflow
