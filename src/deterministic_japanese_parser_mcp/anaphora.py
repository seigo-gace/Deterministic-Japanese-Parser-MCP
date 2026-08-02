import re

from .models import ItemStatus, ReferenceResolution
from .normalizer import span_to_original

PATTERN = re.compile(r"これ|それ|あれ|前の案|先ほどの内容|上記|下記|同じもの|この内容|その件")


class AnaphoraResolver:
    def resolve(
        self,
        text,
        mapping,
        original,
        context: list[str],
        known: list[str],
        max_candidates: int = 8,
    ) -> list[ReferenceResolution]:
        output: list[ReferenceResolution] = []
        # Preserve deterministic order and remove duplicate context strings.
        pool = list(dict.fromkeys(value for value in [*reversed(context), *known] if value))
        for match in PATTERN.finditer(text):
            candidates = pool[:max_candidates]
            selected = candidates[0] if len(candidates) == 1 else None
            status = (
                ItemStatus.RESOLVED
                if selected
                else (ItemStatus.AMBIGUOUS if candidates else ItemStatus.INSUFFICIENT)
            )
            output.append(
                ReferenceResolution(
                    expression=match.group(0),
                    candidates=candidates,
                    selected=selected,
                    span=span_to_original(match.start(), match.end(), mapping, original),
                    status=status,
                )
            )
        return output
