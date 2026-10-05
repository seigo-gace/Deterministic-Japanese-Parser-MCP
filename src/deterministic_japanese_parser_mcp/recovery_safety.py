from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .bounded_recovery import (
    RecoveryDecision,
    SentencePath,
    decide_sentence_recovery,
)


@dataclass(frozen=True)
class SafeRecoveryDecision:
    decision: RecoveryDecision
    blocked_reason: str | None = None

    @property
    def resolved(self) -> bool:
        return self.decision.decision == "RESOLVED" and self.blocked_reason is None


def _path_texts(path: SentencePath) -> tuple[str, str]:
    original = "".join(option.original_text for option in path.options)
    recovered = "".join(path.text_sequence)
    return original, recovered


def changes_protected_element(
    path: SentencePath,
    protected_elements: Sequence[str],
) -> bool:
    """Detect loss/change of protected literal elements across the full path."""
    original, recovered = _path_texts(path)
    for element in protected_elements:
        if not element:
            continue
        original_count = original.count(element)
        if original_count and recovered.count(element) != original_count:
            return True
    return False


def decide_safe_sentence_recovery(
    paths: Sequence[SentencePath],
    *,
    path_scores: Mapping[str, float],
    minimum_score: float,
    minimum_margin: float,
    protected_elements: Sequence[str] = (),
    action_semantics_changed: bool = False,
) -> SafeRecoveryDecision:
    """Apply semantic-safety boundaries after evidence/margin resolution.

    `action_semantics_changed` is supplied by the downstream deterministic
    semantic comparison. Recovery never guesses this value itself.
    """
    decision = decide_sentence_recovery(
        paths,
        path_scores=path_scores,
        minimum_score=minimum_score,
        minimum_margin=minimum_margin,
    )
    if decision.decision != "RESOLVED" or decision.selected_path is None:
        return SafeRecoveryDecision(decision=decision)

    if changes_protected_element(decision.selected_path, protected_elements):
        return SafeRecoveryDecision(
            decision=RecoveryDecision(
                decision="INSUFFICIENT",
                selected_path=None,
                absolute_score=decision.absolute_score,
                margin=decision.margin,
                competing_path_keys=decision.competing_path_keys,
            ),
            blocked_reason="RECOVERY_CHANGED_PROTECTED_ELEMENT",
        )

    if action_semantics_changed:
        return SafeRecoveryDecision(
            decision=RecoveryDecision(
                decision="INSUFFICIENT",
                selected_path=None,
                absolute_score=decision.absolute_score,
                margin=decision.margin,
                competing_path_keys=decision.competing_path_keys,
            ),
            blocked_reason="RECOVERY_CHANGED_ACTION_SEMANTICS",
        )

    return SafeRecoveryDecision(decision=decision)
