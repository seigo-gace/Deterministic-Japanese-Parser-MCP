import re

_ASCII_WORD = re.compile(r"[A-Za-z0-9_]")
_TERMINAL = "\0"


def _compact(text: str) -> str:
    return "".join(text.split())


class Canonicalizer:
    """Map reviewed synonyms and exact-only lexical identities deterministically."""

    _CACHE: dict[str, tuple[dict, dict, int]] = {}

    def __init__(self, synonyms: dict):
        cache_key = synonyms.get("_cache_key")
        cached = self._CACHE.get(cache_key) if cache_key else None
        if cached is not None:
            (
                self.surface_to_ids,
                self.trie,
                self.maximum_surface_length,
            ) = cached
            return

        exact_only = set(synonyms.get("exact_only_groups", []))
        surface_to_ids: dict[str, set[str]] = {}
        trie: dict = {}
        maximum = 0
        for canonical, surfaces in synonyms.get("groups", {}).items():
            for surface in [canonical, *(surfaces or [])]:
                compact = _compact(surface)
                if not compact:
                    continue
                surface_to_ids.setdefault(compact, set()).add(canonical)
                if canonical in exact_only:
                    continue
                maximum = max(maximum, len(compact))
                node = trie
                for char in compact:
                    node = node.setdefault(char, {})
                node.setdefault(_TERMINAL, set()).add(canonical)

        self.surface_to_ids = {
            surface: frozenset(sorted(ids))
            for surface, ids in surface_to_ids.items()
        }
        self.trie = trie
        self.maximum_surface_length = maximum
        if cache_key:
            self._CACHE[cache_key] = (
                self.surface_to_ids,
                self.trie,
                self.maximum_surface_length,
            )
            while len(self._CACHE) > 8:
                self._CACHE.pop(next(iter(self._CACHE)))

    @staticmethod
    def _ascii_boundary(
        text: str,
        start: int,
        end: int,
        surface: str,
    ) -> bool:
        if not surface or not any(
            char.isascii() and char.isalnum()
            for char in surface
        ):
            return True
        left_ok = (
            start == 0
            or _ASCII_WORD.match(text[start - 1]) is None
        )
        right_ok = (
            end == len(text)
            or _ASCII_WORD.match(text[end]) is None
        )
        return left_ok and right_ok

    def exact_ids(self, text: str) -> frozenset[str]:
        compact = _compact(text)
        if not compact:
            return frozenset()
        return self.surface_to_ids.get(compact, frozenset())

    def ids(self, text: str) -> frozenset[str]:
        compact = _compact(text)
        if not compact:
            return frozenset()
        found: set[str] = set(self.exact_ids(compact))
        if not self.trie:
            return frozenset(sorted(found))

        for start in range(len(compact)):
            node = self.trie
            end_limit = min(
                len(compact),
                start + self.maximum_surface_length,
            )
            longest_ids: frozenset[str] | set[str] | None = None
            for index in range(start, end_limit):
                node = node.get(compact[index])
                if node is None:
                    break
                terminal = node.get(_TERMINAL)
                if terminal is not None:
                    end = index + 1
                    surface = compact[start:end]
                    if self._ascii_boundary(
                        compact,
                        start,
                        end,
                        surface,
                    ):
                        longest_ids = terminal
            if longest_ids:
                found.update(longest_ids)
        return frozenset(sorted(found))

    def related(self, left: str, right: str) -> bool:
        left_compact = _compact(left)
        right_compact = _compact(right)
        if not left_compact or not right_compact:
            return False

        left_exact = self.exact_ids(left_compact)
        right_exact = self.exact_ids(right_compact)
        if left_exact and right_exact:
            return bool(left_exact.intersection(right_exact))

        left_ids = self.ids(left_compact)
        right_ids = self.ids(right_compact)
        if left_ids and right_ids and left_ids.intersection(right_ids):
            return True

        # An exact lexical identity must not be equated to a different longer or
        # shorter lexical identity merely because one string contains the other.
        if left_exact or right_exact:
            return False

        minimum = min(len(left_compact), len(right_compact))
        return minimum >= 2 and (
            left_compact in right_compact
            or right_compact in left_compact
        )
