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


def _claim_target(statement: dict) -> str | None:
    value = (
        statement.get("mainsnak", {})
        .get("datavalue", {})
        .get("value")
    )
    if isinstance(value, dict):
        candidate = value.get("id")
    else:
        candidate = value
    return candidate if isinstance(candidate, str) else None


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
        representation = _representation(
            form.get("representations", {})
        )
        if not representation:
            continue
        if representation not in surfaces:
            surfaces.append(representation)
        forms.append({
            "representation": representation,
            "grammatical_features": list(
                form.get("grammaticalFeatures", [])
            ),
        })
        for statement in form.get("claims", {}).get("P898", []):
            value = _claim_target(statement)
            if value and value not in readings:
                readings.append(value)

    senses: list[dict] = []
    for sense in entity.get("senses", []):
        gloss = _representation(sense.get("glosses", {}))
        cross_references: list[str] = []
        claims = sense.get("claims", {})
        for property_id, prefix in (
            ("P5973", "synonym_sense"),
            ("P5974", "antonym_sense"),
        ):
            for statement in claims.get(property_id, []):
                candidate = _claim_target(statement)
                reference = (
                    f"{prefix}:{candidate}" if candidate else None
                )
                if reference and reference not in cross_references:
                    cross_references.append(reference)
        if gloss:
            senses.append({
                "sense_id": sense.get("id"),
                "gloss": gloss,
                "language": "ja",
                "labels": [],
                "domains": [],
                "examples": [],
                "cross_references": cross_references,
            })

    related: list[str] = []
    for statement in entity.get("claims", {}).get("P5191", []):
        candidate = _claim_target(statement)
        relation = (
            f"derived_from_lexeme:{candidate}" if candidate else None
        )
        if relation and relation not in related:
            related.append(relation)

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
    print(
        f"WIKIDATA LEXEME IMPORT OK: records={count} output={args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
