from __future__ import annotations

from deterministic_japanese_parser_mcp.bounded_recovery import (
    LatticeOption,
    RecoveryLimits,
    SentencePath,
)
from deterministic_japanese_parser_mcp.recovery_safety import (
    changes_protected_element,
    decide_safe_sentence_recovery,
)


def _path(*, original: str, recovered: str, unresolved: bool = False) -> SentencePath:
    option = LatticeOption(
        start_token=0,
        end_token_exclusive=1,
        original_text=original,
        candidate_text=recovered,
        candidate_segments=(recovered,),
        recovery_cost=0.5,
        runtime_record_ids=("R1",),
        evidence_ids=("runtime:R1",),
        operations=("substitution",),
        unresolved=unresolved,
    )
    return SentencePath(
        options=(option,),
        recovery_cost=0.5,
        unresolved_count=int(unresolved),
    )


def test_protected_literal_change_is_detected_across_whole_path():
    changed = _path(original="顧客ID-123を確認", recovered="顧客ID-124を確認")
    preserved = _path(original="顧客ID-123を確認", recovered="顧客ID-123を確認する")

    assert changes_protected_element(changed, ["顧客ID-123"]) is True
    assert changes_protected_element(preserved, ["顧客ID-123"]) is False


def test_high_score_cannot_override_protected_element_change():
    changed = _path(original="ID123", recovered="ID124")
    decision = decide_safe_sentence_recovery(
        [changed],
        path_scores={changed.key: 0.99},
        minimum_score=0.8,
        minimum_margin=0.2,
        protected_elements=["ID123"],
    )

    assert decision.resolved is False
    assert decision.decision.decision == "INSUFFICIENT"
    assert decision.blocked_reason == "RECOVERY_CHANGED_PROTECTED_ELEMENT"


def test_high_score_cannot_override_action_semantics_change():
    changed = _path(original="停止しない", recovered="停止する")
    decision = decide_safe_sentence_recovery(
        [changed],
        path_scores={changed.key: 0.99},
        minimum_score=0.8,
        minimum_margin=0.2,
        action_semantics_changed=True,
    )

    assert decision.resolved is False
    assert decision.blocked_reason == "RECOVERY_CHANGED_ACTION_SEMANTICS"


def test_safe_supported_recovery_can_resolve():
    safe = _path(original="かくせい", recovered="がくせい")
    decision = decide_safe_sentence_recovery(
        [safe],
        path_scores={safe.key: 0.95},
        minimum_score=0.8,
        minimum_margin=0.2,
        protected_elements=["別の保護値"],
        action_semantics_changed=False,
    )

    assert decision.resolved is True
    assert decision.blocked_reason is None
