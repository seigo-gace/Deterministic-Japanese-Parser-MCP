from __future__ import annotations

from collections.abc import Callable

from . import reading_runtime
from .models import Proposition

_INSTALLED = False


def _restore_reviewed_exceptions(
    original_propositions: list[Proposition],
    normalized_propositions: list[Proposition],
) -> list[Proposition]:
    """Preserve reviewed exception semantics removed by contrast normalization.

    Reading discourse may represent `ただし` as a `contrasts_with` relation, but
    that relation does not replace the independently reviewed `exception`
    proposition emitted by EXCEPTION rules.  Keeping both layers is required:
    the proposition carries exception semantics while the discourse relation
    carries cross-clause contrast evidence.

    Special cases that intentionally remove an exception proposition (for
    example the gratitude + incomplete-tail rewrite) run before this normalizer;
    therefore only exception propositions present at the normalizer boundary are
    restored here.
    """
    normalized_by_id = {
        item.proposition_id: item for item in normalized_propositions
    }
    original_ids = {
        item.proposition_id for item in original_propositions
    }

    output: list[Proposition] = []
    emitted: set[str] = set()
    for item in original_propositions:
        normalized = normalized_by_id.get(item.proposition_id)
        if normalized is not None:
            output.append(normalized)
            emitted.add(normalized.proposition_id)
            continue
        if item.intent_type == "exception":
            output.append(item)
            emitted.add(item.proposition_id)

    for item in normalized_propositions:
        if item.proposition_id not in original_ids and item.proposition_id not in emitted:
            output.append(item)
            emitted.add(item.proposition_id)

    return output


def install_reading_exception_preservation() -> None:
    """Install the exception-preservation correction once.

    This patch is intentionally narrow: it does not create new exception
    semantics and does not infer from raw text.  It only prevents an already
    reviewed exception proposition from being discarded when the reading layer
    also emits a contrast discourse relation.
    """
    global _INSTALLED
    if _INSTALLED:
        return

    original: Callable = reading_runtime._normalize_concessive_and_contrast_propositions

    def normalize(propositions, **kwargs):
        normalized = original(propositions, **kwargs)
        return _restore_reviewed_exceptions(list(propositions), normalized)

    reading_runtime._normalize_concessive_and_contrast_propositions = normalize
    _INSTALLED = True
