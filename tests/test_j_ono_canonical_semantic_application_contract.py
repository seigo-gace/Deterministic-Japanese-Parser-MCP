from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_j_ono_canonical_semantic_application_keeps_lexical_and_runtime_gated() -> None:
    workflow = (ROOT / ".github/workflows/j-ono-data-quality-audit.yml").read_text(
        encoding="utf-8"
    )
    assert "J_ONO_CANONICAL_SEMANTIC_DECISION_COUNT_MISMATCH" in workflow
    assert "J_ONO_POST_SEMANTIC_PREMATURE_RUNTIME_PROMOTION" in workflow
    assert "J_ONO_CANONICAL_SEMANTIC_APPLICATION=" in workflow
    assert '"semantic_approved_records": semantic_approved' in workflow
    assert '"lexical_source_pos_blockers": lexical_source_blockers' in workflow
    assert '"runtime_eligible_records": runtime_eligible' in workflow
    assert '"automatic_lexical_approval": False' in workflow
    assert '"automatic_pos_fill": False' in workflow
    assert '"runtime_promotion": False' in workflow
    assert "source-part-of-speech-required" in workflow
    assert "approved_meaning_candidates" in workflow
