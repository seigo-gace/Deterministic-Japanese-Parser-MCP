from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Iterator


class LiteralIndex:
    """Deterministic Aho-Corasick index for exact Unicode literals.

    Lookup cost depends on the input length and emitted matches rather than the
    number of registered literals. The index is immutable after construction.
    """

    def __init__(self, literals: Iterable[str]):
        unique = tuple(sorted({value for value in literals if value}))
        self.literal_count = len(unique)
        self._transitions: list[dict[str, int]] = [{}]
        self._failures: list[int] = [0]
        self._outputs: list[list[str]] = [[]]

        for literal in unique:
            state = 0
            for char in literal:
                next_state = self._transitions[state].get(char)
                if next_state is None:
                    next_state = len(self._transitions)
                    self._transitions[state][char] = next_state
                    self._transitions.append({})
                    self._failures.append(0)
                    self._outputs.append([])
                state = next_state
            self._outputs[state].append(literal)

        queue: deque[int] = deque()
        for state in self._transitions[0].values():
            queue.append(state)

        while queue:
            state = queue.popleft()
            for char, next_state in self._transitions[state].items():
                queue.append(next_state)
                failure = self._failures[state]
                while failure and char not in self._transitions[failure]:
                    failure = self._failures[failure]
                self._failures[next_state] = self._transitions[failure].get(char, 0)
                inherited = self._outputs[self._failures[next_state]]
                if inherited:
                    self._outputs[next_state].extend(inherited)

        self._outputs = [
            sorted(set(values), key=lambda value: (-len(value), value))
            for values in self._outputs
        ]
        self._root_chars = frozenset(self._transitions[0])

    @property
    def state_count(self) -> int:
        return len(self._transitions)

    def find(self, text: str) -> Iterator[tuple[str, int, int]]:
        # Every registered literal must start with a root character. Rejecting
        # text without any such character is exact and avoids a Python scan.
        if not text or self._root_chars.isdisjoint(text):
            return
        state = 0
        for end_index, char in enumerate(text, start=1):
            while state and char not in self._transitions[state]:
                state = self._failures[state]
            state = self._transitions[state].get(char, 0)
            for literal in self._outputs[state]:
                yield literal, end_index - len(literal), end_index

    def matched_literals(self, text: str) -> set[str]:
        if not text or self._root_chars.isdisjoint(text):
            return set()
        return {literal for literal, _, _ in self.find(text)}
