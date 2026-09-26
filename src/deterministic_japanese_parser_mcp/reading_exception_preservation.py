from __future__ import annotations

from collections.abc import Callable

from . import reading_runtime
from .models import Proposition

_INSTALLED = False
_CONSTRAINT_INTENTS = {
    "prohibition",
    "preserve",
    "out_of_scope",
    "requirement",
    "constraint",
}


def _restore_reviewed_constraint_exceptions(
    original_propositions: list[Proposition],
    normalized_propositions: list[Proposition],
) -> list[Proposition]:
    """Restore only reviewed `exception` propositions that constrain behavior.

    The reading layer intentionally collapses ordinary `ただし` contrast clauses
    into discourse evidence.  That is correct for a sentence such as
    `公開する。ただし障害なら止める。`, where the actionable predicate is already
    represented directly.

    A reviewed exception must not be discarded, however, when the same clause
    carries an explicit constraint such as prohibition/preservation.  In that
    case the exception proposition is part of the safety/constraint semantics
    and may also be referenced by scope edges.

    This function never rebuilds or reorders the reading runtime output.  It only
    appends missing reviewed exception propositions whose clause contains an
    independently detected constraint intent.  That narrow behavior avoids
    perturbing unrelated rewrites such as gratitude + incomplete-tail handling.
    """
    present_ids = {item.proposition_id for item in normalized_propositions}
    constrained_clause_ids = {
        item.clause_id
        for item in original_propositions
        if item.intent_type in _CONSTRAINT_INTENTS and item.clause_id is not None
    }

    restored = [
        item
        for item in original_propositions
        if item.intent_type == "exception"
        and item.proposition_id not in present_ids
        and item.clause_id in constrained_clause_ids
    ]
    if not restored:
        return normalized_propositions
    return [*normalized_propositions, *restored]


def install_reading_exception_preservation() -> None:
    """Install the narrow exception-constraint preservation correction once."""
    global _INSTALLED
    if _INSTALLED:
        return

    original: Callable = reading_runtime._normalize_concessive_and_contrast_propositions

    def normalize(propositions, **kwargs):
        normalized = original(propositions, **kwargs)
        return _restore_reviewed_constraint_exceptions(
            list(propositions),
            normalized,
        )

    reading_runtime._normalize_concessive_and_contrast_propositions = normalize
    _INSTALLED = True
