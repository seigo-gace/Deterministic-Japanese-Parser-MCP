from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

TOOLS_ROOT = Path(__file__).resolve().parents[2]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dictionary_supply.common import (
    LexiconRecord,
    SourceInfo,
    normalize_text,
    open_binary,
    sha256_file,
    stable_id,
    write_jsonl,
)

_JAPANESE_SECTION = re.compile(
    r"(?ms)^==\s*(?:\{\{(?:ja|jpn)\}\}|日本語)\s*==\s*$"
)
_LEVEL2 = re.compile(r"(?m)^==[^=].*?==\s*$")
_HEADING = re.compile(r"(?m)^(={3,6})\s*(.*?)\s*\1\s*$")
_DEFINITION = re.compile(r"(?m)^#(?![:*#])\s*(.+?)\s*$")
_LIST_ITEM = re.compile(r"(?m)^\*+\s*(.+?)\s*$")
_LINK = re.compile(r"\[\[(?:[^\]|]+\|)?([^\]]+)\]\]")
_TEMPLATE = re.compile(r"\{\{([^{}]+)\}\}")
_TAG = re.compile(r"<[^>]+>")

_POS_HEADINGS = {
    "名詞": "noun",
    "固有名詞": "proper_noun",
    "動詞": "verb",
    "形容詞": "adjective",
    "形容動詞": "adjectival_noun",
    "副詞": "adverb",
    "助詞": "particle",
    "助動詞": "auxiliary_verb",
    "接続詞": "conjunction",
    "感動詞": "interjection",
    "連体詞": "adnominal",
    "代名詞": "pronoun",
    "接頭辞": "prefix",
    "接尾辞": "suffix",
    "成句": "phrase",
    "慣用句": "idiom",
    "ことわざ": "proverb",
}
_RELATION_HEADINGS = {
    "類義語": "synonyms",
    "同義語": "synonyms",
    "対義語": "antonyms",
    "反義語": "antonyms",
    "関連語": "related",
    "派生語": "related",
    "複合語": "related",
    "成句": "related",
}
_READING_HEADINGS = {"発音", "読み", "語源"}


def _clean_wikitext(value: str) -> str:
    value = _TAG.sub(" ", value)
    value = _LINK.sub(lambda match: match.group(1), value)

    def template_value(match: re.Match) -> str:
        parts = [part.strip() for part in match.group(1).split("|")]
        if not parts:
            return ""
        name = parts[0].lower()
        if name in {"ruby", "ふりがな", "読み仮名"} and len(parts) >= 2:
            return parts[1]
        if name in {"context", "label", "タグ", "context label"}:
            return ""
        if len(parts) >= 2 and name in {"l", "link", "m", "mention"}:
            return parts[-1]
        return ""

    previous = None
    while previous != value:
        previous = value
        value = _TEMPLATE.sub(template_value, value)
    value = value.replace("'''", "").replace("''", "")
    value = re.sub(r"\[(?:https?://\S+)\s+([^\]]+)\]", r"\1", value)
    value = re.sub(r"<!--.*?-->", " ", value, flags=re.S)
    value = re.sub(r"&[a-zA-Z]+;", " ", value)
    return normalize_text(value)


def _section(text: str) -> str | None:
    match = _JAPANESE_SECTION.search(text)
    if not match:
        return None
    start = match.end()
    next_section = _LEVEL2.search(text, start)
    return text[start : next_section.start() if next_section else len(text)]


def _split_headings(section: str) -> list[tuple[str, str]]:
    matches = list(_HEADING.finditer(section))
    if not matches:
        return [("", section)]
    output: list[tuple[str, str]] = []
    if matches[0].start() > 0:
        output.append(("", section[: matches[0].start()]))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(section)
        output.append((_clean_wikitext(match.group(2)), section[match.end() : end]))
    return output


def _items(block: str) -> list[str]:
    output: list[str] = []
    for raw in _LIST_ITEM.findall(block):
        value = _clean_wikitext(raw)
        if value and value not in output:
            output.append(value)
    return output


def _readings(section: str, title: str) -> list[str]:
    values: list[str] = []
    patterns = [
        r"(?:よみ|読み|仮名)\s*[=:：]\s*([ぁ-んァ-ヶー]+)",
        r"(?:東京式|京阪式).*?\[([^\]]+)\]",
        r"\{\{(?:ruby|ふりがな|読み仮名)\|[^|{}]+\|([^|{}]+)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, section, flags=re.I | re.S):
            value = normalize_text(match.group(1))
            if value and value != title and value not in values:
                values.append(value)
    if re.fullmatch(r"[ぁ-んァ-ヶー]+", title):
        values.insert(0, title)
    return values


def parse_entry(
    *,
    title: str,
    text: str,
    revision_id: str,
    source_version: str,
    source_sha256: str,
) -> LexiconRecord | None:
    section = _section(text)
    if not section:
        return None
    title = normalize_text(title)
    if not title or title.startswith(("Wiktionary:", "テンプレート:", "カテゴリ:")):
        return None

    pos: list[str] = []
    senses: list[dict] = []
    synonyms: list[str] = []
    antonyms: list[str] = []
    related: list[str] = []
    usage_labels: list[str] = []
    forms: list[dict] = []

    for heading, block in _split_headings(section):
        normalized_heading = re.sub(r"\s+", "", heading)
        for japanese, canonical in _POS_HEADINGS.items():
            if japanese in normalized_heading and canonical not in pos:
                pos.append(canonical)
        relation = next(
            (
                field
                for japanese, field in _RELATION_HEADINGS.items()
                if japanese in normalized_heading
            ),
            None,
        )
        if relation:
            target = {
                "synonyms": synonyms,
                "antonyms": antonyms,
                "related": related,
            }[relation]
            for value in _items(block):
                if value != title and value not in target:
                    target.append(value)
            continue
        if any(label in normalized_heading for label in _READING_HEADINGS):
            continue
        if "活用" in normalized_heading:
            for value in _items(block):
                forms.append({
                    "representation": value,
                    "grammatical_features": ["wiktionary_inflection"],
                })
            continue
        for raw in _DEFINITION.findall(block):
            gloss = _clean_wikitext(raw)
            if not gloss:
                continue
            label_match = re.match(r"^[（(]([^）)]+)[）)]\s*(.*)$", gloss)
            labels: list[str] = []
            if label_match:
                labels = [normalize_text(item) for item in re.split(r"[,、/]", label_match.group(1))]
                gloss = normalize_text(label_match.group(2))
                for label in labels:
                    if label and label not in usage_labels:
                        usage_labels.append(label)
            if gloss:
                senses.append({
                    "gloss": gloss,
                    "language": "ja",
                    "labels": labels,
                    "domains": [],
                    "examples": [],
                    "cross_references": [],
                })

    if not senses and not pos and not synonyms and not related:
        return None
    source = SourceInfo(
        dataset="Japanese Wiktionary",
        version=source_version,
        license="CC-BY-SA-4.0 AND GFDL-1.3-or-later",
        source_id=revision_id or title,
        source_url=f"https://ja.wiktionary.org/wiki/{title}",
        source_sha256=source_sha256,
        attribution="Japanese Wiktionary contributors",
    )
    return LexiconRecord(
        record_id=stable_id("WIKT", title, revision_id),
        lemma=title,
        readings=_readings(section, title),
        surfaces=[title],
        part_of_speech=pos,
        lexical_category=pos[0] if pos else None,
        senses=senses,
        forms=forms,
        synonyms=synonyms,
        antonyms=antonyms,
        related=related,
        usage_labels=usage_labels,
        source=source,
        review_status="needs_review",
    ).normalized()


def import_dump(
    path: Path,
    *,
    source_version: str,
    limit: int | None = None,
) -> list[LexiconRecord]:
    checksum = sha256_file(path)
    records: list[LexiconRecord] = []
    with open_binary(path) as handle:
        context = ET.iterparse(handle, events=("end",))
        for _, element in context:
            if not element.tag.endswith("page"):
                continue
            title = ""
            text = ""
            revision_id = ""
            for child in element.iter():
                local = child.tag.rsplit("}", 1)[-1]
                if local == "title" and child.text:
                    title = child.text
                elif local == "revision":
                    for revision_child in child:
                        revision_local = revision_child.tag.rsplit("}", 1)[-1]
                        if revision_local == "id" and revision_child.text:
                            revision_id = revision_child.text
                        elif revision_local == "text" and revision_child.text:
                            text = revision_child.text
            record = parse_entry(
                title=title,
                text=text,
                revision_id=revision_id,
                source_version=source_version,
                source_sha256=checksum,
            )
            if record is not None:
                records.append(record)
                if limit is not None and len(records) >= limit:
                    break
            element.clear()
    return records


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import the official Japanese Wiktionary XML dump into JSONL."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-version", required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    records = import_dump(
        args.input,
        source_version=args.source_version,
        limit=args.limit,
    )
    count = write_jsonl(args.output, records)
    print(f"WIKTIONARY IMPORT OK: records={count} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
