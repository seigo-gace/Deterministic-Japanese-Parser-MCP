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
    assert "J_ONO_REAL_DATA_HARD_FAILURE" in workflow
    assert "J_ONO_AUTO_MEANING_JUDGEMENT_FORBIDDEN" in workflow
    assert "J_ONO_AUTO_APPROVAL_FORBIDDEN" in workflow
    assert "J_ONO_RUNTIME_PROMOTION_FORBIDDEN" in workflow
    assert "git push" not in workflow
    assert "git commit" not in workflow
