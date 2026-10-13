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


def test_j_ono_three_explicit_lexical_decisions_are_only_promotable_records() -> None:
    workflow = (ROOT / ".github/workflows/j-ono-data-quality-audit.yml").read_text(
        encoding="utf-8"
    )
    assert "J_ONO_CANONICAL_UNAUTHORIZED_LEXICAL_DECISION" in workflow
    assert 'if len(selected) != 840:' in workflow
    assert 'if manifest["decision_count"] != 840:' in workflow
    assert 'manifest["runtime_eligible_records"] != 3' in workflow
    assert '"lexical_source_pos_blockers": (lexical_source_blockers, 834)' in workflow
    assert '"lexical_review_records": (lexical_review, 834)' in workflow
    assert 'ADAPTER-FROZEN-j-ono-definitions-0b8bcf39a2e20af33c861d61' in workflow
    assert '["interjection (kandoushi)"]' in workflow
    assert '"automatic_lexical_approval": False' in workflow
    assert '"runtime_promotion": False' in workflow
    assert 'ADAPTER-FROZEN-j-ono-definitions-0d6493711195aa74959767c4' in workflow
    assert 'ADAPTER-FROZEN-j-ono-definitions-c5ea288d4c27d8b9d5283b4f' in workflow
    assert 'runtime.record_count == 3' in workflow
