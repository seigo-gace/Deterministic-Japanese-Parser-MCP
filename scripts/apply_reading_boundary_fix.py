#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

PATH = Path("src/deterministic_japanese_parser_mcp/reading_runtime.py")


def sub_once(text: str, pattern: str, replacement: str, *, flags: int = 0, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        raise RuntimeError(f"{label}: expected one replacement, got {count}")
    return updated


def main() -> None:
    text = PATH.read_text(encoding="utf-8")

    text = text.replace(
        '(re.compile(r"(?:てもよい|てもいい|許可する)"), "permission"),',
        '(re.compile(r"(?:ても(?:よい|いい|良い|よろしい|大丈夫|構わない|構いません)|でも(?:よい|いい|良い)|許可する)"), "permission"),',
        1,
    )

    text = sub_once(
        text,
        r'_PERMISSION_TE_MO_TAIL = re\.compile\(.*?\n\n\ndef _is_permission_te_mo\(clause_text: str, match: re\.Match\[str\]\) -> bool:\n.*?\n\n',
        '''_PERMISSION_CONSTRUCTION = re.compile(\n    r"(?:ても(?:よい|いい|良い|よろしい|大丈夫|構わない|構いません)|でも(?:よい|いい|良い))"\n)\n\n\ndef _permission_ranges(text: str) -> list[tuple[int, int]]:\n    return [match.span() for match in _PERMISSION_CONSTRUCTION.finditer(text)]\n\n\ndef _is_permission_te_mo(clause_text: str, match: re.Match[str]) -> bool:\n    if match.group(0) not in {"ても", "でも"}:\n        return False\n    return _inside_ranges(match, _permission_ranges(clause_text))\n\n''',
        flags=re.DOTALL,
        label="permission helper",
    )

    helper = '''def _matching_token_entries(\n    match: re.Match[str],\n    tokens: list[Token],\n    *,\n    base_offset: int,\n) -> list[tuple[int, Token]]:\n    start = base_offset + match.start()\n    end = base_offset + match.end()\n    return [\n        (index, token)\n        for index, token in enumerate(tokens)\n        if token.span.start < end and start < token.span.end\n    ]\n\n\ndef _match_is_token_aligned(\n    match: re.Match[str],\n    tokens: list[Token],\n    *,\n    base_offset: int,\n) -> bool:\n    entries = _matching_token_entries(match, tokens, base_offset=base_offset)\n    if not entries:\n        return False\n    start = base_offset + match.start()\n    end = base_offset + match.end()\n    return entries[0][1].span.start == start and entries[-1][1].span.end == end\n\n\ndef _semantic_match_allowed(\n    operator_type: str,\n    semantic_value: str,\n    match: re.Match[str],\n    tokens: list[Token],\n    *,\n    base_offset: int,\n) -> bool:\n    entries = _matching_token_entries(match, tokens, base_offset=base_offset)\n    if not entries:\n        return False\n    marker = match.group(0)\n\n    # Japanese conditional -ば patterns often begin inside the inflected verb\n    # token (e.g. 行け + ば). Require an actual 接続助詞「ば」token rather than\n    # accepting a substring such as 「例えば」.\n    if operator_type == "condition" and marker.endswith("ば"):\n        last = entries[-1][1]\n        return last.surface == "ば" and "接続助詞" in last.pos\n\n    if not _match_is_token_aligned(match, tokens, base_offset=base_offset):\n        return False\n\n    first_index = entries[0][0]\n    first = entries[0][1]\n    previous = tokens[first_index - 1] if first_index > 0 else None\n\n    if operator_type == "condition":\n        if marker == "まで":\n            if previous is None:\n                return False\n            return _pos0(previous) in _PREDICATE_POS or previous.normalized in {\n                "終了", "完了", "終わり", "始まり"\n            }\n        if marker == "と":\n            return _pos0(first) == "助詞" and "接続助詞" in first.pos\n        if marker == "でも":\n            # Noun/pronoun + でも is ambiguous between additive/choice and\n            # concessive readings. Resolve it as a condition only when an\n            # explicit conditional noun licenses that reading.\n            return previous is not None and previous.normalized in {\n                "場合", "条件", "状況", "時"\n            }\n\n    if operator_type == "modality":\n        if semantic_value == "hearsay" and marker == "らしい":\n            return _pos0(first) == "助動詞"\n        if semantic_value == "hearsay" and marker == "そうだ":\n            return first.surface == "そう" and _pos0(first) == "名詞"\n        if semantic_value == "desire" and marker == "たい":\n            return first.normalized == "たい" and _pos0(first) == "助動詞"\n\n    if operator_type == "quantifier" and marker in {"以上", "以下", "未満"}:\n        # Numeric bounds require a nearby numeric token/counter. This excludes\n        # discourse formulae such as 「以上のことから」「以下の通り」.\n        left = max(0, first_index - 3)\n        previous_tokens = tokens[left:first_index]\n        return any(\n            _pos0(token) == "名詞" and "数詞" in token.pos\n            for token in previous_tokens\n        )\n\n    return True\n\n\n'''

    text = text.replace(
        'def _has_semantic_negation(text: str) -> bool:\n',
        helper + 'def _has_semantic_negation(\n    text: str,\n    *,\n    tokens: list[Token] | None = None,\n    base_offset: int = 0,\n) -> bool:\n',
        1,
    )
    text = sub_once(
        text,
        r'def _has_semantic_negation\(\n    text: str,\n    \*,\n    tokens: list\[Token\] \| None = None,\n    base_offset: int = 0,\n\) -> bool:\n.*?\n\n\ndef _scope_target_frame_ids',
        '''def _has_semantic_negation(\n    text: str,\n    *,\n    tokens: list[Token] | None = None,\n    base_offset: int = 0,\n) -> bool:\n    excluded_ranges = [\n        *_polite_request_ranges(text),\n        *_permission_ranges(text),\n    ]\n    for pattern, _ in _NEGATION_PATTERNS:\n        for match in pattern.finditer(text):\n            if _inside_ranges(match, excluded_ranges):\n                continue\n            if tokens is not None and not _semantic_match_allowed(\n                "negation",\n                "negation",\n                match,\n                tokens,\n                base_offset=base_offset,\n            ):\n                continue\n            return True\n    return False\n\n\ndef _scope_target_frame_ids''',
        flags=re.DOTALL,
        label="semantic negation",
    )

    text = sub_once(
        text,
        r'def _voice\(text: str\) -> list\[str\]:\n.*?\n\n\ndef _has_passive_voice',
        '''def _voice(text: str) -> list[str]:\n    if re.search(r"(?:させられる|せられる)", text):\n        return ["causative_passive"]\n    if re.search(r"(?:された|される|されて)", text):\n        return ["passive"]\n    if re.search(\n        r"(?:できる|出来る|話せる|読める|書ける|聞ける|見える|行ける|飲める|食べられる|可能だ|可能です)",\n        text,\n    ):\n        return ["potential"]\n    if re.search(r"(?:させる|(?:読|書|食|飲|見|聞|行|走|書|話)(?:ま|ん)?せ(?:る|た|て))", text):\n        return ["causative"]\n    if re.search(r"(?:られた|られる|られて)", text):\n        if re.search(r"(?:に|によって)[^、。！？!?]{0,24}?(?:られた|られる|られて)", text):\n            return ["passive"]\n        return ["passive_or_potential"]\n    if re.search(r"れる", text):\n        return ["passive_or_potential"]\n    return ["active"]\n\n\ndef _has_passive_voice''',
        flags=re.DOTALL,
        label="voice",
    )

    text = sub_once(
        text,
        r'def _modalities\(text: str\) -> list\[str\]:\n.*?\n\n\ndef _polite_request_ranges',
        '''def _modalities(\n    text: str,\n    *,\n    tokens: list[Token] | None = None,\n    base_offset: int = 0,\n) -> list[str]:\n    values: list[str] = []\n    polite_ranges = _polite_request_ranges(text)\n    for pattern, value in _MODALITY_PATTERNS:\n        for match in pattern.finditer(text):\n            if value == "inference" and _inside_ranges(match, polite_ranges):\n                continue\n            if tokens is not None and not _semantic_match_allowed(\n                "modality",\n                value,\n                match,\n                tokens,\n                base_offset=base_offset,\n            ):\n                continue\n            if value not in values:\n                values.append(value)\n    return values\n\n\ndef _polite_request_ranges''',
        flags=re.DOTALL,
        label="modalities",
    )

    text = text.replace(
        '    start_number: int,\n) -> tuple[list[ScopeOperator], list[dict]]:\n',
        '    start_number: int,\n    tokens: list[Token],\n) -> tuple[list[ScopeOperator], list[dict]]:\n',
        1,
    )
    text = text.replace(
        '    polite_ranges = _polite_request_ranges(clause.text)\n',
        '    polite_ranges = _polite_request_ranges(clause.text)\n    permission_ranges = _permission_ranges(clause.text)\n',
        1,
    )

    old_loops = '''    for pattern, value in _NEGATION_PATTERNS:\n        for match in pattern.finditer(clause.text):\n            if _inside_ranges(match, polite_ranges):\n                continue\n            add("negation", value, match)\n    for pattern, value in _CONDITION_PATTERNS:\n        for match in pattern.finditer(clause.text):\n            if match.group(0) in {"ても", "でも"} and _inside_ranges(\n                match,\n                polite_ranges,\n            ):\n                continue\n            if _is_permission_te_mo(clause.text, match):\n                continue\n            add("condition", value, match)\n    for pattern, value in _MODALITY_PATTERNS:\n        for match in pattern.finditer(clause.text):\n            if value == "inference" and _inside_ranges(match, polite_ranges):\n                continue\n            if (\n                value == "inference"\n                and match.group(0) in {"でしょう", "だろう"}\n                and re.search(r"(?:でしょう|だろう)か[。！？!?]?$", clause.text)\n            ):\n                continue\n            add("modality", value, match)\n    for pattern, value in _QUANTIFIER_PATTERNS:\n        for match in pattern.finditer(clause.text):\n            add("quantifier", value, match)\n'''
    new_loops = '''    for pattern, value in _NEGATION_PATTERNS:\n        for match in pattern.finditer(clause.text):\n            if _inside_ranges(match, polite_ranges) or _inside_ranges(match, permission_ranges):\n                continue\n            if not _semantic_match_allowed(\n                "negation", value, match, tokens, base_offset=clause.source_span.start\n            ):\n                continue\n            add("negation", value, match)\n    for pattern, value in _CONDITION_PATTERNS:\n        for match in pattern.finditer(clause.text):\n            if match.group(0) in {"ても", "でも"} and _inside_ranges(\n                match,\n                polite_ranges,\n            ):\n                continue\n            if _is_permission_te_mo(clause.text, match):\n                continue\n            if not _semantic_match_allowed(\n                "condition", value, match, tokens, base_offset=clause.source_span.start\n            ):\n                continue\n            add("condition", value, match)\n    for pattern, value in _MODALITY_PATTERNS:\n        for match in pattern.finditer(clause.text):\n            if value == "inference" and _inside_ranges(match, polite_ranges):\n                continue\n            if (\n                value == "inference"\n                and match.group(0) in {"でしょう", "だろう"}\n                and re.search(r"(?:でしょう|だろう)か[。！？!?]?$", clause.text)\n            ):\n                continue\n            if not _semantic_match_allowed(\n                "modality", value, match, tokens, base_offset=clause.source_span.start\n            ):\n                continue\n            add("modality", value, match)\n    for pattern, value in _QUANTIFIER_PATTERNS:\n        for match in pattern.finditer(clause.text):\n            if not _semantic_match_allowed(\n                "quantifier", value, match, tokens, base_offset=clause.source_span.start\n            ):\n                continue\n            add("quantifier", value, match)\n'''
    if old_loops not in text:
        raise RuntimeError("operator loops: source block not found")
    text = text.replace(old_loops, new_loops, 1)

    text = text.replace(
        '                        if _has_semantic_negation(clause.text)\n',
        '                        if _has_semantic_negation(\n                            clause.text, tokens=tokens, base_offset=clause.source_span.start\n                        )\n',
        1,
    )
    text = text.replace(
        '                    modality=_modalities(clause.text),\n',
        '                    modality=_modalities(\n                        clause.text, tokens=tokens, base_offset=clause.source_span.start\n                    ),\n',
        1,
    )
    text = text.replace(
        '                        if _has_semantic_negation(local_text)\n',
        '                        if _has_semantic_negation(\n                            local_text, tokens=tokens, base_offset=frame.source_span.start\n                        )\n',
        1,
    )
    text = text.replace(
        '                    "modality": _modalities(local_text),\n',
        '                    "modality": _modalities(\n                        local_text, tokens=tokens, base_offset=frame.source_span.start\n                    ),\n',
        1,
    )
    text = text.replace(
        '                len(operators) + 1,\n            )\n',
        '                len(operators) + 1,\n                tokens,\n            )\n',
        1,
    )

    # Gold G-0148 requires the explicit ただし exception to survive. The old\n    # blanket deletion made repository CI fail before pytest ran.\n    text = text.replace(
        '''    if has_tadashi:\n        filtered = [\n            item\n            for item in filtered\n            if item.intent_type != "exception"\n        ]\n''',
        '''    if has_tadashi:\n        # 「ただし」is both a contrast marker and an explicit exception cue.\n        # Keep the exception proposition; downstream dedupe already removes\n        # exact duplicates.\n        filtered = list(filtered)\n''',
        1,
    )

    # Causal nominal ため is ambiguous in general. Resolve only when the\n    # matrix predicate itself denotes a deterministic adverse outcome/action.\n    marker = '''        if len(clause_frames) < 2:\n            continue\n'''
    insertion = '''        if clause_frames and "のため" in clause.text:\n            main = clause_frames[-1]\n            if main.predicate in {\n                "中止する", "停止する", "延期する", "休止する", "断念する",\n                "失敗する", "遅延する", "欠航する",\n            }:\n                output.append(DiscourseRelation(\n                    relation_id=f"DR-{len(output) + 1:03d}",\n                    source_clause_id=clause.clause_id,\n                    target_clause_id=clause.clause_id,\n                    relation="causes",\n                    marker="のため",\n                    confidence=0.96,\n                ))\n        if len(clause_frames) < 2:\n            continue\n'''
    if marker not in text:
        raise RuntimeError("intra-clause discourse insertion point missing")
    text = text.replace(marker, insertion, 1)

    PATH.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
