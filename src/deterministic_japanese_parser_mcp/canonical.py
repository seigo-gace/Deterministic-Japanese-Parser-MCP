import re

_ASCII_WORD = re.compile(r"[A-Za-z0-9_]")


def _compact(text: str) -> str:
    return "".join(text.split())


class Canonicalizer:
    """Map surfaces to one or more canonical groups without hiding collisions."""

    def __init__(self, synonyms: dict):
        surface_to_ids: dict[str, set[str]] = {}
        for canonical, surfaces in synonyms.get("groups", {}).items():
            for surface in [canonical, *(surfaces or [])]:
                if surface:
                    surface_to_ids.setdefault(surface, set()).add(canonical)
        self.surface_to_ids = {
            surface: frozenset(sorted(ids))
            for surface, ids in surface_to_ids.items()
        }
        by_first: dict[str, list[str]] = {}
        for surface in self.surface_to_ids:
            by_first.setdefault(surface[0], []).append(surface)
        self.by_first = {
            char: tuple(sorted(values, key=lambda item: (-len(item), item)))
            for char, values in by_first.items()
        }

    @staticmethod
    def _ascii_boundary(text: str, start: int, end: int, surface: str) -> bool:
        if not surface or not any(char.isascii() and char.isalnum() for char in surface):
            return True
        left_ok = start == 0 or _ASCII_WORD.match(text[start - 1]) is None
        right_ok = end == len(text) or _ASCII_WORD.match(text[end]) is None
        return left_ok and right_ok

    def ids(self, text: str) -> frozenset[str]:
        compact = _compact(text)
        if not compact:
            return frozenset()
        found: set[str] = set()
        exact = self.surface_to_ids.get(compact)
        if exact:
            found.update(exact)
        for index, char in enumerate(compact):
            for surface in self.by_first.get(char, ()):
                end = index + len(surface)
                if compact.startswith(surface, index) and self._ascii_boundary(
                    compact, index, end, surface
                ):
                    found.update(self.surface_to_ids[surface])
        return frozenset(sorted(found))

    def related(self, left: str, right: str) -> bool:
        left_compact = _compact(left)
        right_compact = _compact(right)
        if not left_compact or not right_compact:
            return False
        left_ids = self.ids(left_compact)
        right_ids = self.ids(right_compact)
        if left_ids and right_ids and left_ids.intersection(right_ids):
            return True
        minimum = min(len(left_compact), len(right_compact))
        return minimum >= 2 and (
            left_compact in right_compact or right_compact in left_compact
        )
