from __future__ import annotations

import argparse
from pathlib import Path
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


def _texts(element: ET.Element, tag: str) -> list[str]:
    output: list[str] = []
    for item in element.findall(tag):
        value = normalize_text(item.text or "")
        if value and value not in output:
            output.append(value)
    return output


def parse_entry(
    entry: ET.Element,
    *,
    source_version: str,
    source_sha256: str,
) -> list[LexiconRecord]:
    sequence = normalize_text(entry.findtext("ent_seq") or "")
    writings = _texts(entry, "k_ele/keb")
    readings = _texts(entry, "r_ele/reb")
    lemmas = writings or readings
    output: list[LexiconRecord] = []
    if not lemmas:
        return output

    senses: list[dict] = []
    all_pos: list[str] = []
    all_domains: list[str] = []
    all_labels: list[str] = []
    synonyms: list[str] = []
    antonyms: list[str] = []
    related: list[str] = []
    for sense_index, sense in enumerate(entry.findall("sense"), 1):
        pos = _texts(sense, "pos")
        fields = _texts(sense, "field")
        misc = _texts(sense, "misc")
        dialect = _texts(sense, "dial")
        cross_references = _texts(sense, "xref")
        antonym_values = _texts(sense, "ant")
        for value in pos:
            if value not in all_pos:
                all_pos.append(value)
        for value in fields:
            if value not in all_domains:
                all_domains.append(value)
        for value in [*misc, *dialect]:
            if value not in all_labels:
                all_labels.append(value)
        for value in cross_references:
            if value not in related:
                related.append(value)
        for value in antonym_values:
            if value not in antonyms:
                antonyms.append(value)
        glosses = []
        for gloss in sense.findall("gloss"):
            value = normalize_text(gloss.text or "")
            if not value:
                continue
            language = gloss.attrib.get("{http://www.w3.org/XML/1998/namespace}lang", "eng")
            glosses.append((language, value))
        for language, gloss in glosses:
            senses.append({
                "sense_id": f"{sequence}-{sense_index}-{language}",
                "gloss": gloss,
                "language": language,
                "labels": [*misc, *dialect],
                "domains": fields,
                "examples": [],
                "cross_references": [*cross_references, *antonym_values],
            })

    for lemma in lemmas:
        source = SourceInfo(
            dataset="JMdict",
            version=source_version,
            license="CC-BY-SA-4.0",
            source_id=sequence or lemma,
            source_url="https://www.edrdg.org/jmdict/j_jmdict.html",
            source_sha256=source_sha256,
            attribution="Electronic Dictionary Research and Development Group",
        )
        output.append(LexiconRecord(
            record_id=stable_id("JMD", sequence, lemma),
            lemma=lemma,
            readings=readings,
            surfaces=[*writings, *readings],
            part_of_speech=all_pos,
            senses=senses,
            synonyms=synonyms,
            antonyms=antonyms,
            related=related,
            domains=all_domains,
            usage_labels=all_labels,
            source=source,
            review_status="needs_review",
            notes=[
                "JMdict glosses are multilingual support evidence; Japanese semantic definitions require review or another Japanese source."
            ],
        ).normalized())
    return output


def import_dump(
    path: Path,
    *,
    source_version: str,
    limit: int | None = None,
) -> list[LexiconRecord]:
    checksum = sha256_file(path)
    output: list[LexiconRecord] = []
    with open_binary(path) as handle:
        for _, element in ET.iterparse(handle, events=("end",)):
            if element.tag != "entry":
                continue
            output.extend(parse_entry(
                element,
                source_version=source_version,
                source_sha256=checksum,
            ))
            element.clear()
            if limit is not None and len(output) >= limit:
                return output[:limit]
    return output


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import JMdict XML into the common JSONL lexicon schema."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-version", required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    count = write_jsonl(
        args.output,
        import_dump(
            args.input,
            source_version=args.source_version,
            limit=args.limit,
        ),
    )
    print(f"JMDICT IMPORT OK: records={count} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
