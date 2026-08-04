from __future__ import annotations

import argparse
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from typing import Iterator

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


def _reading_mappings(entry: ET.Element) -> list[dict]:
    output: list[dict] = []
    for reading_element in entry.findall("r_ele"):
        reading = normalize_text(reading_element.findtext("reb") or "")
        if not reading:
            continue
        output.append({
            "reading": reading,
            "restricted_to": _texts(reading_element, "re_restr"),
            "no_kanji": reading_element.find("re_nokanji") is not None,
        })
    return output


def parse_entry(
    entry: ET.Element,
    *,
    source_version: str,
    source_sha256: str,
    lexical_only: bool = False,
) -> list[LexiconRecord]:
    sequence = normalize_text(entry.findtext("ent_seq") or "")
    writings = _texts(entry, "k_ele/keb")
    reading_mappings = _reading_mappings(entry)
    readings = [item["reading"] for item in reading_mappings]
    lemma_candidates = writings or readings
    if not lemma_candidates:
        return []
    lemma = lemma_candidates[0]

    senses: list[dict] = []
    all_pos: list[str] = []
    all_domains: list[str] = []
    all_labels: list[str] = []
    antonyms: list[str] = []
    related: list[str] = []
    for sense_index, sense in enumerate(entry.findall("sense"), 1):
        pos = _texts(sense, "pos")
        fields = _texts(sense, "field")
        misc = _texts(sense, "misc")
        dialect = _texts(sense, "dial")
        for value in pos:
            if value not in all_pos:
                all_pos.append(value)
        for value in fields:
            if value not in all_domains:
                all_domains.append(value)
        for value in [*misc, *dialect]:
            if value not in all_labels:
                all_labels.append(value)
        if lexical_only:
            continue
        cross_references = _texts(sense, "xref")
        antonym_values = _texts(sense, "ant")
        for value in cross_references:
            if value not in related:
                related.append(value)
        for value in antonym_values:
            if value not in antonyms:
                antonyms.append(value)
        for gloss in sense.findall("gloss"):
            value = normalize_text(gloss.text or "")
            if not value:
                continue
            language = gloss.attrib.get(
                "{http://www.w3.org/XML/1998/namespace}lang",
                "eng",
            )
            senses.append({
                "sense_id": f"{sequence}-{sense_index}-{language}",
                "gloss": value,
                "language": language,
                "labels": [*misc, *dialect],
                "domains": fields,
                "examples": [],
                "cross_references": [
                    *cross_references,
                    *antonym_values,
                ],
            })

    source = SourceInfo(
        dataset="JMdict",
        version=source_version,
        license="CC-BY-SA-4.0",
        source_id=sequence or lemma,
        source_url="https://www.edrdg.org/jmdict/j_jmdict.html",
        source_sha256=source_sha256,
        attribution=(
            "Electronic Dictionary Research and Development Group"
        ),
    )
    notes = [
        (
            "Imported in lexical-identity-only mode; readings are preserved as "
            "metadata and are not promoted as orthographic aliases."
        )
        if lexical_only
        else (
            "JMdict glosses are multilingual support evidence; Japanese semantic "
            "definitions require review or another Japanese source."
        )
    ]
    return [LexiconRecord(
        record_id=stable_id("JMD", sequence, lemma),
        lemma=lemma,
        readings=readings,
        reading_mappings=reading_mappings,
        surfaces=writings or [lemma],
        part_of_speech=all_pos,
        senses=senses,
        antonyms=antonyms,
        related=related,
        domains=all_domains,
        usage_labels=all_labels,
        source=source,
        review_status="needs_review",
        notes=notes,
    ).normalized()]


def iter_dump(
    path: Path,
    *,
    source_version: str,
    limit: int | None = None,
    lexical_only: bool = False,
) -> Iterator[LexiconRecord]:
    checksum = sha256_file(path)
    emitted = 0
    with open_binary(path) as handle:
        for _, element in ET.iterparse(handle, events=("end",)):
            if element.tag != "entry":
                continue
            for record in parse_entry(
                element,
                source_version=source_version,
                source_sha256=checksum,
                lexical_only=lexical_only,
            ):
                yield record
                emitted += 1
                if limit is not None and emitted >= limit:
                    return
            element.clear()


def import_dump(
    path: Path,
    *,
    source_version: str,
    limit: int | None = None,
    lexical_only: bool = False,
) -> list[LexiconRecord]:
    return list(iter_dump(
        path,
        source_version=source_version,
        limit=limit,
        lexical_only=lexical_only,
    ))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import JMdict XML into the common JSONL lexicon schema."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-version", required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--lexical-only",
        action="store_true",
        help=(
            "Import lemma, orthographic surfaces, readings, reading restrictions, "
            "POS and labels without semantic relations."
        ),
    )
    args = parser.parse_args()
    count = write_jsonl(
        args.output,
        iter_dump(
            args.input,
            source_version=args.source_version,
            limit=args.limit,
            lexical_only=args.lexical_only,
        ),
    )
    print(
        "JMDICT IMPORT OK: "
        f"records={count} lexical_only={args.lexical_only} "
        f"output={args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
