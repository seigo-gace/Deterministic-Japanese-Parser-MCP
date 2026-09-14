#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

import apply_reading_boundary_fix_v2 as phase1

PATH = Path("src/deterministic_japanese_parser_mcp/reading_runtime.py")


def block(*lines: str) -> str:
    return "\n".join(lines) + "\n"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one source block, got {count}")
    return text.replace(old, new, 1)


def main() -> None:
    phase1.main()
    text = PATH.read_text(encoding="utf-8")

    old_voice = block(
        "def _voice(text: str) -> list[str]:",
        '    if re.search(r"(?:させられる|せられる)", text):',
        '        return ["causative_passive"]',
        '    if re.search(r"(?:された|される|されて|られた|られる|られて)", text):',
        '        return ["passive"]',
        "    if re.search(",
        '        r"(?:できる|出来る|話せる|読める|書ける|聞ける|見える|行ける|飲める|食べられる|可能だ|可能です)",',
        "        text,",
        "    ):",
        '        return ["potential"]',
        '    if re.search(r"(?:させる|(?:読|書|食|飲|見|聞|行|走|書|話)(?:ま|ん)?せ(?:る|た|て))", text):',
        '        return ["causative"]',
        '    if re.search(r"(?:られる|れる)", text):',
        '        return ["passive_or_potential"]',
        '    return ["active"]',
    )
    new_voice = block(
        "def _voice(text: str) -> list[str]:",
        '    if re.search(r"(?:させられる|せられる)", text):',
        '        return ["causative_passive"]',
        '    if re.search(r"(?:された|される|されて)", text):',
        '        return ["passive"]',
        "    if re.search(",
        '        r"(?:できる|出来る|話せる|読める|書ける|聞ける|見える|行ける|飲める|可能だ|可能です)",',
        "        text,",
        "    ):",
        '        return ["potential"]',
        '    if re.search(r"(?:させる|(?:読|書|食|飲|見|聞|行|走|書|話)(?:ま|ん)?せ(?:る|た|て))", text):',
        '        return ["causative"]',
        '    if re.search(r"(?:られた|られる|られて)", text):',
        '        if re.search(r"(?:に|によって)[^、。！？!?]{0,24}?(?:られた|られる|られて)", text):',
        '            return ["passive"]',
        '        return ["passive_or_potential"]',
        '    if re.search(r"れる", text):',
        '        return ["passive_or_potential"]',
        '    return ["active"]',
    )
    text = replace_once(text, old_voice, new_voice, "rareru voice ambiguity")

    old_tadashi = block(
        "    if has_tadashi:",
        "        filtered = [",
        "            item",
        "            for item in filtered",
        '            if item.intent_type != "exception"',
        "        ]",
    )
    new_tadashi = block(
        "    if has_tadashi:",
        "        # ただし is itself an explicit exception cue; keep the exception proposition.",
        "        filtered = list(filtered)",
    )
    text = replace_once(text, old_tadashi, new_tadashi, "tadashi exception preservation")

    old_relation_gate = block(
        "        if len(clause_frames) < 2:",
        "            continue",
    )
    new_relation_gate = block(
        "        if clause_frames and re.search(",
        '            r"(?:雨|雪|台風|暴風|事故|故障|災害|停電|渋滞|病気|障害)のため"',
        '            r"[^、。！？!?]{0,40}(?:中止|停止|延期|休止|断念|欠航|遅延|失敗)",',
        "            clause.text,",
        "        ):",
        "            output.append(DiscourseRelation(",
        '                relation_id=f"DR-{len(output) + 1:03d}",',
        "                source_clause_id=clause.clause_id,",
        "                target_clause_id=clause.clause_id,",
        '                relation="causes",',
        '                marker="のため",',
        "                confidence=0.96,",
        "            ))",
        "        if len(clause_frames) < 2:",
        "            continue",
    )
    text = replace_once(text, old_relation_gate, new_relation_gate, "nominal cause relation")

    PATH.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
