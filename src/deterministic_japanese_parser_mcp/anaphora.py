import re

from .canonical import Canonicalizer
from .models import Intent, ItemStatus, ReferenceResolution
from .normalizer import span_to_original

PATTERN = re.compile(
    r"これ|それ|あれ|それら|両方|前者|後者|前の案|先ほどの内容|"
    r"上記|下記|同じもの|この内容|その件|同ページ|同ファイル|"
    r"同リポジトリ|同ブランチ|"
    r"(?:この|その|あの)(?:API|UI|DB|ページ|ファイル|案|仕様|内容|"
    r"リポジトリ|ブランチ|設定|資料)|"
    r"直前の[^、。！？]+|以前の[^、。！？]+"
)
_HEAD_PREFIX = re.compile(
    r"^(?:直前の|以前の|前の|先ほどの|上記の?|下記の?|この|その|あの|同)"
)
_GENERIC = {
    "これ",
    "それ",
    "あれ",
    "それら",
    "両方",
    "上記",
    "下記",
    "同じもの",
    "この内容",
    "その件",
    "先ほどの内容",
}


class AnaphoraResolver:
    def __init__(self, canonicalizer: Canonicalizer | None = None):
        self.canonicalizer = canonicalizer

    @staticmethod
    def mentions_from_intents(intents: list[Intent]) -> list[str]:
        values: list[tuple[int, str]] = []
        for intent in intents:
            if intent.type == "reference":
                continue
            for key in (
                "target",
                "task",
                "action",
                "new",
                "old",
                "scope",
                "dependency",
                "premise",
            ):
                value = intent.captures.get(key)
                if value:
                    cleaned = value.strip(" 、。！？!?「」『』\"'")
                    if cleaned:
                        values.append((intent.span.start, cleaned))
        return list(dict.fromkeys(value for _, value in sorted(values)))

    @staticmethod
    def _head(reference: str) -> str:
        value = _HEAD_PREFIX.sub("", reference).strip()
        return value if value and value != reference else ""

    @staticmethod
    def _pool(
        current_mentions: list[str],
        context: list[str],
        known: list[str],
    ) -> list[tuple[str, str, int]]:
        output: list[tuple[str, str, int]] = []
        seen: set[str] = set()
        for rank, value in enumerate(reversed(current_mentions)):
            if value and value not in seen:
                output.append((value, "current", rank))
                seen.add(value)
        for rank, value in enumerate(reversed(context)):
            if value and value not in seen:
                output.append((value, "context", rank))
                seen.add(value)
        for rank, value in enumerate(reversed(known)):
            if value and value not in seen:
                output.append((value, "known", rank))
                seen.add(value)
        return output

    def _related(self, left: str, right: str) -> bool:
        if not left or not right:
            return False
        if left in right or right in left:
            return True
        return bool(
            self.canonicalizer
            and self.canonicalizer.related(left, right)
        )

    def _score(
        self,
        reference: str,
        candidate: str,
        source: str,
        rank: int,
    ) -> int:
        base = {
            "current": 100,
            "context": 70,
            "known": 55,
        }[source]
        score = base - min(30, rank * 4)
        head = self._head(reference)
        if head:
            if head == candidate:
                score += 130
            elif head in candidate:
                score += 100
            elif candidate in head:
                score += 60
            elif self._related(head, candidate):
                score += 45
            else:
                score -= 80
        if reference.startswith("同") and head and head in candidate:
            score += 25
        return score

    def resolve_intents(
        self,
        reference_intents: list[Intent],
        context: list[str],
        known: list[str],
        max_candidates: int = 8,
        current_mentions: list[str] | None = None,
    ) -> list[ReferenceResolution]:
        output: list[ReferenceResolution] = []
        current_mentions = current_mentions or []
        pool = self._pool(current_mentions, context, known)

        for intent in reference_intents:
            reference = intent.value
            if reference == "前者":
                pair = [value for value in context[-2:] if value]
                selected = pair[0] if len(pair) == 2 else None
                candidates = pair
                scores = {
                    value: 200 - index for index, value in enumerate(pair)
                }
                reason = "ordered_pair:first" if selected else None
            elif reference == "後者":
                pair = [value for value in context[-2:] if value]
                selected = pair[1] if len(pair) == 2 else None
                candidates = pair
                scores = {
                    value: 200 - index for index, value in enumerate(reversed(pair))
                }
                reason = "ordered_pair:last" if selected else None
            else:
                ranked = sorted(
                    (
                        (
                            self._score(reference, value, source, rank),
                            value,
                            source,
                        )
                        for value, source, rank in pool
                    ),
                    key=lambda item: (-item[0], item[1]),
                )
                ranked = [item for item in ranked if item[0] > 0]
                candidates = [item[1] for item in ranked[:max_candidates]]
                scores = {
                    value: score for score, value, _ in ranked[:max_candidates]
                }
                selected = None
                reason = None
                if ranked:
                    top = ranked[0]
                    second = ranked[1][0] if len(ranked) > 1 else -999
                    head = self._head(reference)
                    if (
                        len(ranked) == 1
                        or (
                            top[0] >= 100
                            and top[0] - second >= 20
                            and (head or top[2] == "current")
                        )
                    ):
                        selected = top[1]
                        reason = f"ranked:{top[2]}:{top[0]}"

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
                expression=reference,
                candidates=candidates,
                selected=selected,
                candidate_scores=scores,
                resolution_reason=reason,
                span=intent.span,
                status=status,
            ))
        return output

    def discover(
        self,
        text,
        mapping,
        original,
    ) -> list[Intent]:
        return [
            Intent(
                type="reference",
                value=match.group(0),
                captures={"reference": match.group(0)},
                rule_id="REFERENCE-DISCOVERY",
                priority=5,
                span=span_to_original(
                    match.start(), match.end(), mapping, original
                ),
                status=ItemStatus.RESOLVED,
            )
            for match in PATTERN.finditer(text)
        ]

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
        return self.resolve_intents(
            self.discover(text, mapping, original),
            context,
            known,
            max_candidates,
        )
