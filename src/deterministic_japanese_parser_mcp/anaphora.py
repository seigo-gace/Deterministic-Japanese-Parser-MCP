import re

from .models import Intent, ItemStatus, ReferenceResolution
from .normalizer import span_to_original

PATTERN = re.compile(
    r"これ|それ|あれ|前の案|先ほどの内容|上記|下記|同じもの|この内容|その件|"
    r"直前の[^、。！？]+|以前の[^、。！？]+"
)
_HEAD_PREFIX = re.compile(
    r"^(?:直前の|以前の|前の|先ほどの|上記の?|下記の?|この|その|あの)"
)
_GENERIC = {
    "これ",
    "それ",
    "あれ",
    "上記",
    "下記",
    "同じもの",
    "この内容",
    "その件",
    "先ほどの内容",
}


class AnaphoraResolver:
    @staticmethod
    def _pool(context: list[str], known: list[str]) -> list[str]:
        return list(
            dict.fromkeys(value for value in [*reversed(context), *known] if value)
        )

    @staticmethod
    def _head(reference: str) -> str:
        value = _HEAD_PREFIX.sub("", reference).strip()
        return value if value and value != reference else ""

    def _candidates(
        self,
        reference: str,
        pool: list[str],
        max_candidates: int,
    ) -> list[str]:
        if reference in _GENERIC:
            return pool[:max_candidates]
        head = self._head(reference)
        if not head:
            return pool[:max_candidates]
        matched = [candidate for candidate in pool if head in candidate]
        return matched[:max_candidates]

    def resolve_intents(
        self,
        reference_intents: list[Intent],
        context: list[str],
        known: list[str],
        max_candidates: int = 8,
    ) -> list[ReferenceResolution]:
        output: list[ReferenceResolution] = []
        pool = self._pool(context, known)
        for intent in reference_intents:
            candidates = self._candidates(intent.value, pool, max_candidates)
            selected = candidates[0] if len(candidates) == 1 else None
            status = (
                ItemStatus.RESOLVED
                if selected
                else (
                    ItemStatus.AMBIGUOUS
                    if candidates
                    else ItemStatus.INSUFFICIENT
                )
            )
            output.append(ReferenceResolution(
                expression=intent.value,
                candidates=candidates,
                selected=selected,
                span=intent.span,
                status=status,
            ))
        return output

    def resolve(
        self,
        text,
        mapping,
        original,
        context: list[str],
        known: list[str],
        max_candidates: int = 8,
    ) -> list[ReferenceResolution]:
        """Backward-compatible fallback for direct internal callers."""
        intents = [
            Intent(
                type="reference",
                value=match.group(0),
                captures={"reference": match.group(0)},
                rule_id=None,
                priority=0,
                span=span_to_original(
                    match.start(), match.end(), mapping, original
                ),
                status=ItemStatus.RESOLVED,
            )
            for match in PATTERN.finditer(text)
        ]
        return self.resolve_intents(intents, context, known, max_candidates)
