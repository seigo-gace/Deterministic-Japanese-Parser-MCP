from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

TOOLS_ROOT = Path(__file__).resolve().parents[2]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dictionary_supply.common import (
    LexiconRecord,
    SourceInfo,
    normalize_text,
    open_text,
    sha256_file,
    stable_id,
    write_jsonl,
)

JAPANESE_LANGUAGE_ITEM = "Q5287"


def _representation(value: dict, language: str = "ja") -> str | None:
    item = value.get(language)
    if isinstance(item, dict):
        return normalize_text(item.get("value", "")) or None
    return None


def parse_lexeme(
    entity: dict,
    *,
    source_version: str,
    source_sha256: str,
) -> LexiconRecord | None:
    if entity.get("type") != "lexeme":
        return None
    if entity.get("language") != JAPANESE_LANGUAGE_ITEM:
        return None
    lemma = _representation(entity.get("lemmas", {}))
    if not lemma:
        return None
    forms: list[dict] = []
    surfaces: list[str] = [lemma]
    readings: list[str] = []
    for form in entity.get("forms", []):
        representation = _representation(form.get("representations", {}))
        if not representation:
            continue
        if representation not in surfaces:
            surfaces.append(representation)
        forms.append({
            "representation": representation,
            "grammatical_features": list(form.get("grammaticalFeatures", [])),
        })
        for statement in form.get("claims", {}).get("P898", []):
            value = (
                statement.get("mainsnak", {})
                .get("datavalue", {})
                .get("value")
            )
            if isinstance(value, str) and value not in readings:
                readings.append(value)
    senses: list[dict] = []
    synonyms: list[str] = []
    antonyms: list[str] = []
    related: list[str] = []
    for sense in entity.get("senses", []):
        gloss = _representation(sense.get("glosses", {}))
        if gloss:
            senses.append({
                "sense_id": sense.get("id"),
                "gloss": gloss,
                "language": "ja",
                "labels": [],
                "domains": [],
                "examples": [],
                "cross_references": [],
            })
        claims = sense.get("claims", {})
        for property_id, target in (
            ("P5973", synonyms),
            ("P5974", antonyms),
            ("P5191", related),
        ):
            for statement in claims.get(property_id, []):
                value = (
                    statement.get("mainsnak", {})
                    .get("datavalue", {})
                    .get("value")
                )
                if isinstance(value, dict):
                    candidate = value.get("id")
                else:
                    candidate = value
                if isinstance(candidate, str) and candidate not in target:
                    target.append(candidate)
    entity_id = entity.get("id", stable_id("LEXEME", lemma))
    source = SourceInfo(
        dataset="Wikidata Lexemes",
        version=source_version,
        license="CC0-1.0",
        source_id=entity_id,
        source_url=f"https://www.wikidata.org/wiki/Lexeme:{entity_id}",
        source_sha256=source_sha256,
        attribution="Wikidata contributors",
    )
    return LexiconRecord(
        record_id=stable_id("WDL", entity_id, lemma),
        lemma=lemma,
        readings=readings,
        surfaces=surfaces,
        lexical_category=entity.get("lexicalCategory"),
        senses=senses,
        forms=forms,
        synonyms=synonyms,
        antonyms=antonyms,
        related=related,
        source=source,
        review_status="needs_review",
    ).normalized()


def _iter_entities(path: Path):
    with open_text(path) as handle:
        first = ""
        while True:
            char = handle.read(1)
            if not char:
                return
            if not char.isspace():
                first = char
                break
        if first == "[":
            buffer = ""
            decoder = json.JSONDecoder()
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                buffer += chunk
                while True:
                    buffer = buffer.lstrip(" \t\r\n,")
                    if not buffer or buffer.startswith("]"):
                        break
                    try:
                        value, index = decoder.raw_decode(buffer)
                    except json.JSONDecodeError:
                        break
                    yield value
                    buffer = buffer[index:]
            return
        line = first + handle.readline()
        if line.strip().rstrip(","):
            yield json.loads(line.strip().rstrip(","))
        for line in handle:
            value = line.strip().rstrip(",")
            if value and value not in {"[", "]"}:
                yield json.loads(value)


def import_dump(
    path: Path,
    *,
    source_version: str,
    limit: int | None = None,
) -> list[LexiconRecord]:
    checksum = sha256_file(path)
    output: list[LexiconRecord] = []
    for entity in _iter_entities(path):
        record = parse_lexeme(
            entity,
            source_version=source_version,
            source_sha256=checksum,
        )
        if record is not None:
            output.append(record)
            if limit is not None and len(output) >= limit:
                break
    return output


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import Japanese Wikidata Lexemes from a JSON dump."
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
    print(f"WIKIDATA LEXEME IMPORT OK: records={count} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
