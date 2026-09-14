#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

PATH = Path("src/deterministic_japanese_parser_mcp/reading_runtime.py")


def block(*lines: str) -> str:
    return "\n".join(lines) + "\n"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one source block, got {count}")
    return text.replace(old, new, 1)


def main() -> None:
    text = PATH.read_text(encoding="utf-8")

    text = replace_once(
        text,
        '    (re.compile(r"(?:てもよい|てもいい|許可する)"), "permission"),\n',
        '    (re.compile(r"(?:ても(?:よい|いい|良い|よろしい|大丈夫|構わない|構いません)|でも(?:よい|いい|良い)|許可する)"), "permission"),\n',
        "permission modality pattern",
    )

    old_permission = block(
        "_PERMISSION_TE_MO_TAIL = re.compile(",
        '    r"(?:よい|いい|良い|か|よろし)",',
        ")",
        "",
        "",
        "def _is_permission_te_mo(clause_text: str, match: re.Match[str]) -> bool:",
        '    if match.group(0) != "ても":',
        "        return False",
        "    tail = clause_text[match.end():]",
        "    return bool(_PERMISSION_TE_MO_TAIL.match(tail))",
    )
    new_permission = block(
        "_PERMISSION_CONSTRUCTION = re.compile(",
        '    r"(?:ても(?:よい|いい|良い|よろしい|大丈夫|構わない|構いません)|でも(?:よい|いい|良い))"',
        ")",
        "",
        "",
        "def _permission_ranges(text: str) -> list[tuple[int, int]]:",
        "    return [match.span() for match in _PERMISSION_CONSTRUCTION.finditer(text)]",
        "",
        "",
        "def _is_permission_te_mo(clause_text: str, match: re.Match[str]) -> bool:",
        '    if match.group(0) not in {"ても", "でも"}:',
        "        return False",
        "    return _inside_ranges(match, _permission_ranges(clause_text))",
    )
    text = replace_once(text, old_permission, new_permission, "permission helper")

    old_modalities = block(
        "def _modalities(text: str) -> list[str]:",
        "    values: list[str] = []",
        "    polite_ranges = _polite_request_ranges(text)",
        "    for pattern, value in _MODALITY_PATTERNS:",
        "        for match in pattern.finditer(text):",
        '            if value == "inference" and _inside_ranges(match, polite_ranges):',
        "                continue",
        "            if value not in values:",
        "                values.append(value)",
        "    return values",
    )
    new_modalities = block(
        "def _modalities(",
        "    text: str,",
        "    *,",
        "    tokens: list[Token] | None = None,",
        "    base_offset: int = 0,",
        ") -> list[str]:",
        "    values: list[str] = []",
        "    polite_ranges = _polite_request_ranges(text)",
        "    for pattern, value in _MODALITY_PATTERNS:",
        "        for match in pattern.finditer(text):",
        '            if value == "inference" and _inside_ranges(match, polite_ranges):',
        "                continue",
        "            if tokens is not None and not _semantic_match_allowed(",
        '                "modality", value, match, tokens, base_offset=base_offset',
        "            ):",
        "                continue",
        "            if value not in values:",
        "                values.append(value)",
        "    return values",
    )
    text = replace_once(text, old_modalities, new_modalities, "modalities")

    old_negation = block(
        "def _has_semantic_negation(text: str) -> bool:",
        "    polite_ranges = _polite_request_ranges(text)",
        "    return any(",
        "        not _inside_ranges(match, polite_ranges)",
        "        for pattern, _ in _NEGATION_PATTERNS",
        "        for match in pattern.finditer(text)",
        "    )",
    )
    helper_and_negation = block(
        "def _matching_token_entries(",
        "    match: re.Match[str],",
        "    tokens: list[Token],",
        "    *,",
        "    base_offset: int,",
        ") -> list[tuple[int, Token]]:",
        "    start = base_offset + match.start()",
        "    end = base_offset + match.end()",
        "    return [",
        "        (index, token)",
        "        for index, token in enumerate(tokens)",
        "        if token.span.start < end and start < token.span.end",
        "    ]",
        "",
        "",
        "def _match_is_token_aligned(",
        "    match: re.Match[str],",
        "    tokens: list[Token],",
        "    *,",
        "    base_offset: int,",
        ") -> bool:",
        "    entries = _matching_token_entries(match, tokens, base_offset=base_offset)",
        "    if not entries:",
        "        return False",
        "    start = base_offset + match.start()",
        "    end = base_offset + match.end()",
        "    return entries[0][1].span.start == start and entries[-1][1].span.end == end",
        "",
        "",
        "def _semantic_match_allowed(",
        "    operator_type: str,",
        "    semantic_value: str,",
        "    match: re.Match[str],",
        "    tokens: list[Token],",
        "    *,",
        "    base_offset: int,",
        ") -> bool:",
        "    entries = _matching_token_entries(match, tokens, base_offset=base_offset)",
        "    if not entries:",
        "        return False",
        "    marker = match.group(0)",
        "",
        '    if operator_type == "condition" and marker.endswith("ば"):',
        "        last = entries[-1][1]",
        '        return last.surface == "ば" and "接続助詞" in last.pos',
        "",
        "    if not _match_is_token_aligned(match, tokens, base_offset=base_offset):",
        "        return False",
        "",
        "    first_index = entries[0][0]",
        "    first = entries[0][1]",
        "    previous = tokens[first_index - 1] if first_index > 0 else None",
        "",
        '    if operator_type == "condition":',
        '        if marker == "まで":',
        "            if previous is None:",
        "                return False",
        "            return _pos0(previous) in _PREDICATE_POS or previous.normalized in {",
        '                "終了", "完了", "終わり", "始まり"',
        "            }",
        '        if marker == "と":',
        '            return _pos0(first) == "助詞" and "接続助詞" in first.pos',
        '        if marker == "でも":',
        "            return previous is not None and previous.normalized in {",
        '                "場合", "条件", "状況", "時"',
        "            }",
        "",
        '    if operator_type == "modality":',
        '        if semantic_value == "hearsay" and marker == "らしい":',
        '            return _pos0(first) == "助動詞"',
        '        if semantic_value == "hearsay" and marker == "そうだ":',
        '            return first.surface == "そう" and _pos0(first) == "名詞"',
        '        if semantic_value == "desire" and marker == "たい":',
        '            return first.normalized == "たい" and _pos0(first) == "助動詞"',
        "",
        '    if operator_type == "quantifier" and marker in {"以上", "以下", "未満"}:',
        "        tail = match.string[match.end():]",
        '        if marker == "以上" and tail.startswith("のこと"):',
        "            return False",
        '        if marker == "以下" and (tail.startswith("の通り") or tail.startswith("のとおり")):',
        "            return False",
        "",
        "    return True",
        "",
        "",
        "def _has_semantic_negation(",
        "    text: str,",
        "    *,",
        "    tokens: list[Token] | None = None,",
        "    base_offset: int = 0,",
        ") -> bool:",
        "    excluded_ranges = [*_polite_request_ranges(text), *_permission_ranges(text)]",
        "    for pattern, _ in _NEGATION_PATTERNS:",
        "        for match in pattern.finditer(text):",
        "            if _inside_ranges(match, excluded_ranges):",
        "                continue",
        "            if tokens is not None and not _semantic_match_allowed(",
        '                "negation", "negation", match, tokens, base_offset=base_offset',
        "            ):",
        "                continue",
        "            return True",
        "    return False",
    )
    text = replace_once(text, old_negation, helper_and_negation, "semantic matching helper")

    old_sig = block(
        "def _operators_for_clause(",
        "    clause: Clause,",
        "    original: str,",
        "    frames: list[PredicateFrame],",
        "    start_number: int,",
        ") -> tuple[list[ScopeOperator], list[dict]]:",
    )
    new_sig = block(
        "def _operators_for_clause(",
        "    clause: Clause,",
        "    original: str,",
        "    frames: list[PredicateFrame],",
        "    start_number: int,",
        "    tokens: list[Token],",
        ") -> tuple[list[ScopeOperator], list[dict]]:",
    )
    text = replace_once(text, old_sig, new_sig, "operator signature")

    text = replace_once(
        text,
        "    polite_ranges = _polite_request_ranges(clause.text)\n\n    def add(\n",
        "    polite_ranges = _polite_request_ranges(clause.text)\n    permission_ranges = _permission_ranges(clause.text)\n\n    def add(\n",
        "operator ranges",
    )

    old_loops = block(
        "    for pattern, value in _NEGATION_PATTERNS:",
        "        for match in pattern.finditer(clause.text):",
        "            if _inside_ranges(match, polite_ranges):",
        "                continue",
        '            add("negation", value, match)',
        "    for pattern, value in _CONDITION_PATTERNS:",
        "        for match in pattern.finditer(clause.text):",
        '            if match.group(0) in {"ても", "でも"} and _inside_ranges(',
        "                match,",
        "                polite_ranges,",
        "            ):",
        "                continue",
        "            if _is_permission_te_mo(clause.text, match):",
        "                continue",
        '            add("condition", value, match)',
        "    for pattern, value in _MODALITY_PATTERNS:",
        "        for match in pattern.finditer(clause.text):",
        '            if value == "inference" and _inside_ranges(match, polite_ranges):',
        "                continue",
        "            if (",
        '                value == "inference"',
        '                and match.group(0) in {"でしょう", "だろう"}',
        '                and re.search(r"(?:でしょう|だろう)か[。！？!?]?$", clause.text)',
        "            ):",
        "                continue",
        '            add("modality", value, match)',
        "    for pattern, value in _QUANTIFIER_PATTERNS:",
        "        for match in pattern.finditer(clause.text):",
        '            add("quantifier", value, match)',
    )
    new_loops = block(
        "    for pattern, value in _NEGATION_PATTERNS:",
        "        for match in pattern.finditer(clause.text):",
        "            if _inside_ranges(match, polite_ranges) or _inside_ranges(match, permission_ranges):",
        "                continue",
        "            if not _semantic_match_allowed(",
        '                "negation", value, match, tokens, base_offset=clause.source_span.start',
        "            ):",
        "                continue",
        '            add("negation", value, match)',
        "    for pattern, value in _CONDITION_PATTERNS:",
        "        for match in pattern.finditer(clause.text):",
        '            if match.group(0) in {"ても", "でも"} and _inside_ranges(',
        "                match, polite_ranges",
        "            ):",
        "                continue",
        "            if _is_permission_te_mo(clause.text, match):",
        "                continue",
        "            if not _semantic_match_allowed(",
        '                "condition", value, match, tokens, base_offset=clause.source_span.start',
        "            ):",
        "                continue",
        '            add("condition", value, match)',
        "    for pattern, value in _MODALITY_PATTERNS:",
        "        for match in pattern.finditer(clause.text):",
        '            if value == "inference" and _inside_ranges(match, polite_ranges):',
        "                continue",
        "            if (",
        '                value == "inference"',
        '                and match.group(0) in {"でしょう", "だろう"}',
        '                and re.search(r"(?:でしょう|だろう)か[。！？!?]?$", clause.text)',
        "            ):",
        "                continue",
        "            if not _semantic_match_allowed(",
        '                "modality", value, match, tokens, base_offset=clause.source_span.start',
        "            ):",
        "                continue",
        '            add("modality", value, match)',
        "    for pattern, value in _QUANTIFIER_PATTERNS:",
        "        for match in pattern.finditer(clause.text):",
        "            if not _semantic_match_allowed(",
        '                "quantifier", value, match, tokens, base_offset=clause.source_span.start',
        "            ):",
        "                continue",
        '            add("quantifier", value, match)',
    )
    text = replace_once(text, old_loops, new_loops, "operator loops")

    text = replace_once(
        text,
        "                len(operators) + 1,\n            )\n",
        "                len(operators) + 1,\n                tokens,\n            )\n",
        "operator call",
    )

    text = replace_once(
        text,
        "                        if _has_semantic_negation(clause.text)\n",
        "                        if _has_semantic_negation(\n                            clause.text, tokens=tokens, base_offset=clause.source_span.start\n                        )\n",
        "clause negation call",
    )
    text = replace_once(
        text,
        "                    modality=_modalities(clause.text),\n",
        "                    modality=_modalities(\n                        clause.text, tokens=tokens, base_offset=clause.source_span.start\n                    ),\n",
        "clause modality call",
    )
    text = replace_once(
        text,
        "                        if _has_semantic_negation(local_text)\n",
        "                        if _has_semantic_negation(\n                            local_text, tokens=tokens, base_offset=frame.source_span.start\n                        )\n",
        "frame negation call",
    )
    text = replace_once(
        text,
        '                    "modality": _modalities(local_text),\n',
        '                    "modality": _modalities(\n                        local_text, tokens=tokens, base_offset=frame.source_span.start\n                    ),\n',
        "frame modality call",
    )

    PATH.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
