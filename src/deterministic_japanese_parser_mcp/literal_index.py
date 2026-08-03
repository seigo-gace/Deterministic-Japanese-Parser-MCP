from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Iterator
import re


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

        # Every literal must contain its own leading prefix. Searching the
        # deduplicated prefix set in C provides an exact negative filter before
        # the Python Aho-Corasick traversal. Four characters are selective for
        # Japanese rules while keeping the compiled expression compact.
        prefixes = {
            literal[: min(4, len(literal))]
            for literal in unique
        }
        prefix_expression = "|".join(
            re.escape(prefix)
            for prefix in sorted(prefixes, key=lambda value: (-len(value), value))
        )
        self._prefix_pattern = (
            re.compile(f"(?:{prefix_expression})") if prefix_expression else None
        )

    @property
    def state_count(self) -> int:
        return len(self._transitions)

    def _has_possible_match(self, text: str) -> bool:
        # This is exact, not heuristic: if no registered literal prefix exists
        # in the text, no complete registered literal can exist either.
        return bool(
            text
            and self._prefix_pattern
            and self._prefix_pattern.search(text)
        )

    def find(self, text: str) -> Iterator[tuple[str, int, int]]:
        if not self._has_possible_match(text):
            return
        state = 0
        for end_index, char in enumerate(text, start=1):
            while state and char not in self._transitions[state]:
                state = self._failures[state]
            state = self._transitions[state].get(char, 0)
            for literal in self._outputs[state]:
                yield literal, end_index - len(literal), end_index

    def matched_literals(self, text: str) -> set[str]:
        if not self._has_possible_match(text):
            return set()
        return {literal for literal, _, _ in self.find(text)}
