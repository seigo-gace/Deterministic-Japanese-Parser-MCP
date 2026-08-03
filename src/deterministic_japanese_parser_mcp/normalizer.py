import re
import unicodedata

import regex

from .models import OriginalSpan

_PROTECTED = re.compile(r"```[\s\S]*?```|`[^`]*`|https?://[^\s]+")
_GRAPHEME = regex.compile(r"\X")


def extract_protected_ranges(text: str) -> list[tuple[int, int]]:
    return [(match.start(), match.end()) for match in _PROTECTED.finditer(text)]


def _append_protected(
    text: str,
    start: int,
    end: int,
    output: list[str],
    mapping: list[tuple[int, int]],
) -> None:
    for index in range(start, end):
        output.append(text[index])
        mapping.append((index, index + 1))


def _append_normalized(
    text: str,
    start: int,
    end: int,
    output: list[str],
    mapping: list[tuple[int, int]],
) -> None:
    segment = text[start:end]
    for match in _GRAPHEME.finditer(segment):
        absolute_start = start + match.start()
        absolute_end = start + match.end()
        normalized = unicodedata.normalize("NFKC", match.group(0))
        for char in normalized:
            output.append(char)
            mapping.append((absolute_start, absolute_end))


def normalize_with_map(text: str) -> tuple[str, list[tuple[int, int]]]:
    """Normalize non-protected text by grapheme cluster and retain original spans."""
    output: list[str] = []
    mapping: list[tuple[int, int]] = []
    cursor = 0
    for start, end in extract_protected_ranges(text):
        if cursor < start:
            _append_normalized(text, cursor, start, output, mapping)
        _append_protected(text, start, end, output, mapping)
        cursor = end
    if cursor < len(text):
        _append_normalized(text, cursor, len(text), output, mapping)
    return "".join(output), mapping


def span_to_original(
    start: int,
    end: int,
    mapping: list[tuple[int, int]],
    original: str,
) -> OriginalSpan:
    if not mapping:
        return OriginalSpan(start=0, end=0, source_text="")
    start = max(0, min(start, len(mapping) - 1))
    end = max(start + 1, min(end, len(mapping)))
    original_start = mapping[start][0]
    original_end = mapping[end - 1][1]
    return OriginalSpan(
        start=original_start,
        end=original_end,
        source_text=original[original_start:original_end],
    )
