from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Iterator
from typing import Any


class LiteralIndex:
    """Deterministic Aho-Corasick index for exact Unicode literals.

    Lookup cost depends on the input length and emitted matches rather than the
    number of registered literals. The index is immutable after construction.
    Compilers may serialize the automaton with :meth:`to_compiled`; runtime code
    can restore it with :meth:`from_compiled` without rebuilding failure links.
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
        self._build_prefix_gate(unique)

    def _build_prefix_gate(self, literals: Iterable[str]) -> None:
        prefixes_by_first: dict[str, set[str]] = {}
        for literal in literals:
            if not literal:
                continue
            prefix = literal[: min(4, len(literal))]
            prefixes_by_first.setdefault(prefix[0], set()).add(prefix)
        self._prefixes_by_first = {
            first: tuple(sorted(values, key=lambda value: (-len(value), value)))
            for first, values in prefixes_by_first.items()
        }
        self._root_chars = frozenset(prefixes_by_first)

    @classmethod
    def from_compiled(cls, payload: dict[str, Any]) -> "LiteralIndex":
        """Load a validated, precompiled automaton without rebuilding it."""
        obj = cls.__new__(cls)
        transitions = payload.get("transitions")
        failures = payload.get("failures")
        outputs = payload.get("outputs")
        prefixes = payload.get("prefixes_by_first")
        if not isinstance(transitions, list) or not transitions:
            raise ValueError("compiled literal index transitions are required")
        if not isinstance(failures, list) or not isinstance(outputs, list):
            raise ValueError("compiled literal index failures/outputs are required")
        if not (len(transitions) == len(failures) == len(outputs)):
            raise ValueError("compiled literal index arrays must have equal length")
        obj._transitions = [
            {str(char): int(target) for char, target in state.items()}
            for state in transitions
        ]
        obj._failures = [int(value) for value in failures]
        obj._outputs = [
            [str(value) for value in values]
            for values in outputs
        ]
        state_count = len(obj._transitions)
        if any(value < 0 or value >= state_count for value in obj._failures):
            raise ValueError("compiled literal index has invalid failure state")
        for state in obj._transitions:
            if any(target < 0 or target >= state_count for target in state.values()):
                raise ValueError("compiled literal index has invalid transition state")
        if not isinstance(prefixes, dict):
            raise ValueError("compiled literal index prefixes_by_first are required")
        obj._prefixes_by_first = {
            str(first): tuple(str(value) for value in values)
            for first, values in prefixes.items()
        }
        obj._root_chars = frozenset(obj._prefixes_by_first)
        obj.literal_count = int(payload.get("literal_count", 0))
        emitted = {
            literal
            for values in obj._outputs
            for literal in values
        }
        if obj.literal_count != len(emitted):
            raise ValueError("compiled literal index literal_count mismatch")
        return obj

    def to_compiled(self) -> dict[str, Any]:
        """Return a stable JSON-compatible representation of this automaton."""
        return {
            "schema_version": "1.0.0",
            "literal_count": self.literal_count,
            "state_count": self.state_count,
            "transitions": [
                dict(sorted(state.items())) for state in self._transitions
            ],
            "failures": list(self._failures),
            "outputs": [list(values) for values in self._outputs],
            "prefixes_by_first": {
                key: list(values)
                for key, values in sorted(self._prefixes_by_first.items())
            },
        }

    @property
    def state_count(self) -> int:
        return len(self._transitions)

    def _has_possible_match(self, text: str) -> bool:
        """Reject text lacking every exact leading prefix."""
        if not text:
            return False
        present_roots = self._root_chars.intersection(text)
        for first in present_roots:
            for prefix in self._prefixes_by_first[first]:
                if prefix in text:
                    return True
        return False

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
