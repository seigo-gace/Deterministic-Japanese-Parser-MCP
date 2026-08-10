#!/usr/bin/env python3
"""Normalize the canonical TEI Lex-0 Hatoma dictionary from a fixed GitHub snapshot.

The repository contains the current dictionary at /tei/hatoma.tei plus an old
historical .tei copy, a sample XML and a template. All XML/TEI members are
inspected and inventoried, but only the exact canonical member suffix
/tei/hatoma.tei is normalized. Every canonical <entry> is preserved as XML and
emitted once. Only non-empty direct <def> children of direct <sense> children are
lexical meaning evidence. Empty definitions remain needs-evidence. No LLM or
Runtime promotion occurs here.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any
import xml.etree.ElementTree as ET
import zipfile

import public_hatoma_sources as base

CANONICAL_SUFFIX = "/tei/hatoma.tei"
EXPECTED_ARCHIVE_SHA256 = "8c46de727be8d19ae8d7b5b88af343b39630646c8df6a32b692c7bba1c577ac3"
EXPECTED_CANONICAL_SHA256 = "12e8d33c7b34e526a57c2eaa3cbfd05860975643a1b7629dc0758361cb4df99b"
EXPECTED_LICENSE_SHA256 = "87a816969906840bf7af8d4d01cdfad4741b18946365e1f286007935509f2edb"
EXPECTED_ENTRY_COUNT = 16946
EXPECTED_SENSE_COUNT = 18327
EXPECTED_DEF_COUNT = 18346
EXPECTED_NONEMPTY_DEF_COUNT = 18342
EXPECTED_EMPTY_DEF_COUNT = 4
EXPECTED_EXAMPLE_COUNT = 34155
EXPECTED_TRANSLATION_COUNT = 34155
EXPECTED_FORM_COUNT = 16732
EXPECTED_ORTH_COUNT = 16732
EXPECTED_MEDIA_COUNT = 16732
EXPECTED_LICENSE_TEXT = "Attribution-ShareAlike 4.0 International"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return base.sha256_file(path)


def text(element: ET.Element | None) -> str:
    return base.normalized_text(element)


def local(tag: Any) -> str:
    return base.local_name(tag)


def attrs(element: ET.Element) -> dict[str, str]:
    return base.attrs_plain(element)


def direct(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in list(element) if local(child.tag) == name]


def parse_form(form: ET.Element) -> dict[str, Any]:
    orthographies: list[dict[str, Any]] = []
    pronunciations: list[dict[str, Any]] = []
    media_refs: list[dict[str, Any]] = []
    for child in list(form):
        name = local(child.tag)
        if name == "orth":
            value = text(child)
            if value:
                orthographies.append({"text": value, "attributes": attrs(child)})
        elif name == "pron":
            value = text(child)
            if value:
                pronunciations.append({"text": value, "attributes": attrs(child)})
        elif name == "media":
            media_refs.append({
                "text": text(child),
                "attributes": attrs(child),
                "mime_type": child.attrib.get("mimeType", ""),
                "url": child.attrib.get("url", ""),
            })
    return {
        "attributes": attrs(form),
        "orthographies": orthographies,
        "pronunciations": pronunciations,
        "media_refs": media_refs,
    }


def parse_translation(cit: ET.Element) -> dict[str, Any]:
    quotes = []
    for child in list(cit):
        if local(child.tag) == "quote":
            value = text(child)
            if value:
                quotes.append({"text": value, "attributes": attrs(child)})
    return {"attributes": attrs(cit), "quotes": quotes}


def parse_example(cit: ET.Element) -> dict[str, Any]:
    quotes: list[dict[str, Any]] = []
    pronunciations: list[dict[str, Any]] = []
    translations: list[dict[str, Any]] = []
    for child in list(cit):
        name = local(child.tag)
        if name == "quote":
            value = text(child)
            if value:
                quotes.append({"text": value, "attributes": attrs(child)})
        elif name == "pron":
            value = text(child)
            if value:
                pronunciations.append({"text": value, "attributes": attrs(child)})
        elif name == "cit" and child.attrib.get("type") == "translation":
            translations.append(parse_translation(child))
    return {
        "attributes": attrs(cit),
        "quotes": quotes,
        "pronunciations": pronunciations,
        "translations": translations,
    }


def parse_sense(sense: ET.Element, index: int) -> dict[str, Any]:
    definitions = []
    grams = []
    usages = []
    examples = []
    notes = []
    for child in list(sense):
        name = local(child.tag)
        if name == "def":
            definitions.append({"text": text(child), "attributes": attrs(child)})
        elif name == "gramGrp":
            for gram in child.iter():
                if local(gram.tag) == "gram":
                    value = text(gram)
                    if value:
                        grams.append({"text": value, "attributes": attrs(gram)})
        elif name == "usg":
            value = text(child)
            if value:
                usages.append({"text": value, "attributes": attrs(child)})
        elif name == "cit" and child.attrib.get("type") == "example":
            examples.append(parse_example(child))
        elif name == "note":
            value = text(child)
            if value:
                notes.append({"text": value, "attributes": attrs(child)})
    nonempty = [item for item in definitions if item["text"]]
    return {
        "sense_index": index,
        "sense_id": sense.attrib.get(base.XML_ID, ""),
        "attributes": attrs(sense),
        "definitions": definitions,
        "nonempty_definitions": nonempty,
        "grammatical_labels": grams,
        "usages": usages,
        "examples": examples,
        "notes": notes,
        "meaning_complete": bool(nonempty),
    }


def inspect_archive(
    archive_path: Path, manifest: dict[str, Any]
) -> tuple[list[dict[str, Any]], str, bytes, ET.Element, str, bytes]:
    archive_sha = sha256_file(archive_path)
    if archive_sha != EXPECTED_ARCHIVE_SHA256:
        raise RuntimeError(f"Hatoma source archive digest changed: {archive_sha}")
    inspections: list[dict[str, Any]] = []
    canonical_matches: list[tuple[str, bytes, ET.Element]] = []
    license_matches: list[tuple[str, bytes]] = []
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            basename = PurePosixPath(info.filename).name
            if basename == manifest["license"]["license_file"]:
                license_matches.append((info.filename, archive.read(info)))
            suffix = PurePosixPath(info.filename).suffix.casefold()
            if suffix not in {".xml", ".tei"}:
                continue
            payload = archive.read(info)
            item: dict[str, Any] = {
                "member": info.filename,
                "extension": suffix,
                "bytes": len(payload),
                "sha256": sha256_bytes(payload),
                "canonical": info.filename.endswith(CANONICAL_SUFFIX),
            }
            try:
                root = ET.fromstring(payload)
            except ET.ParseError as exc:
                item.update({"parsed": False, "parse_error": str(exc), "root": "", "entry_count": 0})
                inspections.append(item)
                continue
            editions = [
                text(element) for element in root.iter()
                if local(element.tag) == "edition" and text(element)
            ]
            license_targets = [
                element.attrib.get("target", "") for element in root.iter()
                if local(element.tag) in {"licence", "license"} and element.attrib.get("target")
            ]
            entry_count = sum(1 for element in root.iter() if local(element.tag) == "entry")
            item.update({
                "parsed": True,
                "root": local(root.tag),
                "entry_count": entry_count,
                "editions": editions,
                "license_targets": license_targets,
            })
            inspections.append(item)
            if item["canonical"]:
                canonical_matches.append((info.filename, payload, root))

    failures = [item for item in inspections if item["parsed"] is False]
    if failures:
        raise RuntimeError(f"Hatoma XML/TEI parse failure: count={len(failures)} sample={failures[:10]}")
    if len(canonical_matches) != 1:
        raise RuntimeError(f"Hatoma canonical member not unique: {[item[0] for item in canonical_matches]}")
    if len(license_matches) != 1:
        raise RuntimeError(f"Hatoma LICENSE.txt not unique: {[item[0] for item in license_matches]}")

    canonical_member, canonical_payload, canonical_root = canonical_matches[0]
    canonical_sha = sha256_bytes(canonical_payload)
    if canonical_sha != EXPECTED_CANONICAL_SHA256:
        raise RuntimeError(f"Hatoma canonical TEI digest changed: {canonical_sha}")
    if local(canonical_root.tag) != "TEI":
        raise RuntimeError(f"Hatoma canonical root changed: {canonical_root.tag}")
    editions = [text(e) for e in canonical_root.iter() if local(e.tag) == "edition" and text(e)]
    targets = [
        e.attrib.get("target", "") for e in canonical_root.iter()
        if local(e.tag) in {"licence", "license"} and e.attrib.get("target")
    ]
    if manifest["tei_edition"] not in editions:
        raise RuntimeError(f"Hatoma canonical edition mismatch: {editions}")
    if manifest["license"]["license_url"] not in targets:
        raise RuntimeError(f"Hatoma canonical license target mismatch: {targets}")

    license_member, license_payload = license_matches[0]
    license_sha = sha256_bytes(license_payload)
    if license_sha != EXPECTED_LICENSE_SHA256:
        raise RuntimeError(f"Hatoma license digest changed: {license_sha}")
    if EXPECTED_LICENSE_TEXT not in license_payload.decode("utf-8", errors="strict"):
        raise RuntimeError("Hatoma LICENSE.txt no longer contains CC BY-SA 4.0 text")
    return inspections, canonical_member, canonical_payload, canonical_root, license_member, license_payload


def normalize(
    archive_path: Path,
    output_root: Path,
    report_path: Path,
    lock_path: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    inspections, member, payload, root, license_member, license_payload = inspect_archive(archive_path, manifest)
    archive_sha = sha256_file(archive_path)
    canonical_sha = sha256_bytes(payload)
    license_sha = sha256_bytes(license_payload)

    source_root = output_root / "source"
    reference_root = output_root / "reference"
    preserved_root = output_root / "preserved"
    unresolved_root = output_root / "unresolved"
    for directory in (source_root, reference_root, preserved_root, unresolved_root):
        directory.mkdir(parents=True, exist_ok=True)

    canonical_path = source_root / "hatoma.tei"
    license_path = source_root / "LICENSE.txt"
    inventory_path = source_root / "tei-member-inventory.jsonl"
    canonical_path.write_bytes(payload)
    license_path.write_bytes(license_payload)
    with inventory_path.open("w", encoding="utf-8", newline="\n") as handle:
        for item in inspections:
            disposition = "canonical_data_source" if item["canonical"] else "inventory_only_not_normalized"
            handle.write(json.dumps(
                {**item, "disposition": disposition},
                ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ) + "\n")

    reference_path = reference_root / "hatoma-dictionary.jsonl"
    preserved_path = preserved_root / "hatoma-entry-subtrees.jsonl"
    unresolved_path = unresolved_root / "hatoma-missing-definition.jsonl"

    entries = [element for element in root.iter() if local(element.tag) == "entry"]
    source_counts = Counter(local(element.tag) for element in root.iter())
    if len(entries) != EXPECTED_ENTRY_COUNT:
        raise RuntimeError(f"Hatoma canonical entry count changed: {len(entries)}")
    if source_counts["sense"] != EXPECTED_SENSE_COUNT:
        raise RuntimeError(f"Hatoma source sense count changed: {source_counts['sense']}")
    if source_counts["def"] != EXPECTED_DEF_COUNT:
        raise RuntimeError(f"Hatoma source def count changed: {source_counts['def']}")

    normalized_records = 0
    preserved_records = 0
    complete_entries = 0
    unresolved_entries = 0
    normalized_senses = 0
    normalized_defs = 0
    nonempty_defs = 0
    empty_defs = 0
    examples = 0
    translations = 0
    forms = 0
    orthographies = 0
    media_refs = 0
    pos_counts: Counter[str] = Counter()

    with (
        reference_path.open("w", encoding="utf-8", newline="\n") as reference,
        preserved_path.open("w", encoding="utf-8", newline="\n") as preserved,
        unresolved_path.open("w", encoding="utf-8", newline="\n") as unresolved,
    ):
        for entry_index, entry in enumerate(entries, 1):
            entry_xml = ET.tostring(entry, encoding="utf-8")
            entry_sha = sha256_bytes(entry_xml)
            entry_id = entry.attrib.get(base.XML_ID, "") or f"ENTRY-{entry_index:06d}"

            parsed_forms = [parse_form(form) for form in direct(entry, "form")]
            forms += len(parsed_forms)
            orthographies += sum(len(item["orthographies"]) for item in parsed_forms)
            media_refs += sum(len(item["media_refs"]) for item in parsed_forms)
            surfaces = [
                orth["text"] for form in parsed_forms for orth in form["orthographies"] if orth["text"]
            ]

            sense_elements = direct(entry, "sense")
            parsed_senses = [parse_sense(sense, idx) for idx, sense in enumerate(sense_elements, 1)]
            normalized_senses += len(parsed_senses)
            entry_defs = [d for sense in parsed_senses for d in sense["definitions"]]
            entry_nonempty_defs = [d for sense in parsed_senses for d in sense["nonempty_definitions"]]
            normalized_defs += len(entry_defs)
            nonempty_defs += len(entry_nonempty_defs)
            empty_defs += sum(1 for d in entry_defs if not d["text"])
            examples += sum(len(sense["examples"]) for sense in parsed_senses)
            translations += sum(
                len(example["translations"])
                for sense in parsed_senses
                for example in sense["examples"]
            )

            entry_grams = []
            for gramgrp in direct(entry, "gramGrp"):
                for gram in gramgrp.iter():
                    if local(gram.tag) == "gram":
                        value = text(gram)
                        if value:
                            entry_grams.append({"text": value, "attributes": attrs(gram)})
                            pos_counts[value] += 1

            missing_senses = [
                sense["sense_index"] for sense in parsed_senses if not sense["meaning_complete"]
            ]
            complete = bool(parsed_senses) and not missing_senses and bool(entry_nonempty_defs)
            if complete:
                complete_entries += 1
            else:
                unresolved_entries += 1
                unresolved.write(json.dumps({
                    "entry_id": entry_id,
                    "entry_index": entry_index,
                    "surfaces": surfaces,
                    "sense_count": len(parsed_senses),
                    "definition_count": len(entry_defs),
                    "nonempty_definition_count": len(entry_nonempty_defs),
                    "senses_missing_definition": missing_senses,
                    "source_entry_xml_sha256": entry_sha,
                    "reason": "HATOMA_DEFINITION_INCOMPLETE",
                    "review_status": "needs-evidence",
                    "runtime_eligible": False,
                }, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")

            preserved.write(json.dumps({
                "entry_id": entry_id,
                "entry_index": entry_index,
                "source_entry_xml_sha256": entry_sha,
                "entry_xml": entry_xml.decode("utf-8"),
            }, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
            preserved_records += 1

            reference.write(json.dumps({
                "record_id": f"{manifest['id']}:{entry_id}",
                "entry_index": entry_index,
                "entry_id": entry_id,
                "surfaces": surfaces,
                "forms": parsed_forms,
                "grammatical_labels": entry_grams,
                "senses": parsed_senses,
                "meanings": [item["text"] for item in entry_nonempty_defs],
                "meaning_complete": complete,
                "source_entry_xml_sha256": entry_sha,
                "source": {
                    "dataset": manifest["title"],
                    "publisher": manifest["publisher"],
                    "official_dataset_page": manifest["official_dataset_page"],
                    "upstream_repository": manifest["upstream_repository"],
                    "upstream_commit": manifest["upstream_commit"],
                    "source_archive_sha256": archive_sha,
                    "canonical_member": member,
                    "canonical_member_sha256": canonical_sha,
                    "license": manifest["license"]["name"],
                    "license_url": manifest["license"]["license_url"],
                    "attribution": manifest["license"]["attribution"],
                    "tei_edition": manifest["tei_edition"],
                },
                "evidence_status": "reference_only",
                "runtime_eligible": False,
                "llm_generated": False,
            }, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
            normalized_records += 1

    expected = {
        "normalized_records": EXPECTED_ENTRY_COUNT,
        "preserved_records": EXPECTED_ENTRY_COUNT,
        "normalized_sense_records": EXPECTED_SENSE_COUNT,
        "definition_elements": EXPECTED_DEF_COUNT,
        "nonempty_definitions": EXPECTED_NONEMPTY_DEF_COUNT,
        "empty_definitions": EXPECTED_EMPTY_DEF_COUNT,
        "meaning_complete_records": 16942,
        "unresolved_entries": 4,
        "example_records": EXPECTED_EXAMPLE_COUNT,
        "translation_records": EXPECTED_TRANSLATION_COUNT,
        "form_records": EXPECTED_FORM_COUNT,
        "orthography_records": EXPECTED_ORTH_COUNT,
        "media_reference_records": EXPECTED_MEDIA_COUNT,
    }
    observed = {
        "normalized_records": normalized_records,
        "preserved_records": preserved_records,
        "normalized_sense_records": normalized_senses,
        "definition_elements": normalized_defs,
        "nonempty_definitions": nonempty_defs,
        "empty_definitions": empty_defs,
        "meaning_complete_records": complete_entries,
        "unresolved_entries": unresolved_entries,
        "example_records": examples,
        "translation_records": translations,
        "form_records": forms,
        "orthography_records": orthographies,
        "media_reference_records": media_refs,
    }
    if observed != expected:
        raise RuntimeError(f"Hatoma canonical preservation/count mismatch: observed={observed} expected={expected}")

    outputs = []
    for path in (canonical_path, license_path, inventory_path, reference_path, preserved_path, unresolved_path):
        outputs.append({"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)})

    report = {
        "schema_version": manifest["schema_version"],
        "status": "NORMALIZED",
        "source_id": manifest["id"],
        "upstream_commit": manifest["upstream_commit"],
        "source_archive_bytes": archive_path.stat().st_size,
        "source_archive_sha256": archive_sha,
        "canonical_member": member,
        "canonical_member_bytes": len(payload),
        "canonical_member_sha256": canonical_sha,
        "license_member": license_member,
        "license_bytes": len(license_payload),
        "license_sha256": license_sha,
        "tei_members_inspected": len(inspections),
        "tei_member_inventory": inspections,
        "source_element_counts": dict(sorted(source_counts.items())),
        **observed,
        "pos_counts": dict(sorted(pos_counts.items())),
        "output_files": outputs,
        "definition_fabricated": False,
        "llm_api_used": False,
        "web_scraping_used": False,
        "runtime_promotion": False,
    }
    lock = {
        "source_id": manifest["id"],
        "upstream_commit": manifest["upstream_commit"],
        "source_url": manifest["source_url"],
        "source_archive_sha256": archive_sha,
        "canonical_member": member,
        "canonical_member_sha256": canonical_sha,
        "license_sha256": license_sha,
        "entries": normalized_records,
        "inventory_sha256": sha256_file(inventory_path),
        "outputs": outputs,
        "license": manifest["license"],
        "lock_state": "fixed-commit-exact-canonical-tei-and-computed-content-digests",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lock_path.write_text(json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def self_test() -> dict[str, Any]:
    entry = ET.fromstring(
        '<entry xmlns="http://www.tei-c.org/ns/1.0" xml:id="HATOMA.X">'
        '<form><orth>語</orth><pron notation="IPA">go</pron><media mimeType="audio/wav" url="x.wav"/></form>'
        '<gramGrp><gram>名</gram></gramGrp>'
        '<sense><def xml:lang="ja">意味</def><cit type="example"><quote>例</quote>'
        '<cit type="translation"><quote xml:lang="ja">訳</quote></cit></cit></sense></entry>'
    )
    forms = [parse_form(x) for x in direct(entry, "form")]
    senses = [parse_sense(x, i) for i, x in enumerate(direct(entry, "sense"), 1)]
    if forms[0]["media_refs"][0]["url"] != "x.wav":
        raise RuntimeError("Hatoma self-test media reference lost")
    if senses[0]["nonempty_definitions"][0]["text"] != "意味":
        raise RuntimeError("Hatoma self-test definition lost")
    if senses[0]["examples"][0]["translations"][0]["quotes"][0]["text"] != "訳":
        raise RuntimeError("Hatoma self-test translation lost")
    return {"status": "PASS", "forms": 1, "senses": 1, "definitions": 1, "media": 1}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--lock", type=Path)
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test(), ensure_ascii=False, sort_keys=True))
        return 0
    if any(value is None for value in (args.manifest, args.archive, args.output_root, args.report, args.lock)):
        parser.error("--manifest --archive --output-root --report --lock are required")
    manifest = base.load_manifest(args.manifest)
    report = normalize(args.archive, args.output_root, args.report, args.lock, manifest)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
