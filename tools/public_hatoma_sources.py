#!/usr/bin/env python3
"""Normalize the source-locked NINJAL Hatoma-Japanese TEI Lex-0 dictionary.

The fixed upstream repository ZIP is treated as the source artifact. The adapter
selects the TEI dictionary document by structure (TEI root and maximum entry count),
preserves the exact selected XML payload and license file, serializes every entry
subtree, and emits a normalized reference record for every entry. Only TEI <def>
content is accepted as lexical meaning evidence. Missing definitions are kept in an
unresolved inventory; no meaning is generated and no record is promoted to Runtime.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Any
import xml.etree.ElementTree as ET
import zipfile

XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
EXPECTED_LICENSE_TEXT = "Attribution-ShareAlike 4.0 International"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def local_name(tag: Any) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def normalized_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return " ".join("".join(element.itertext()).split())


def descendants(element: ET.Element, name: str) -> list[ET.Element]:
    return [item for item in element.iter() if local_name(item.tag) == name]


def direct_children(element: ET.Element, name: str) -> list[ET.Element]:
    return [item for item in list(element) if local_name(item.tag) == name]


def first_descendant(element: ET.Element, name: str) -> ET.Element | None:
    for item in element.iter():
        if local_name(item.tag) == name:
            return item
    return None


def attrs_plain(element: ET.Element) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in element.attrib.items():
        if key == XML_ID:
            result["xml:id"] = value
        elif key == XML_LANG:
            result["xml:lang"] = value
        else:
            result[local_name(key)] = value
    return dict(sorted(result.items()))


def element_summary(element: ET.Element) -> dict[str, Any]:
    return {
        "tag": local_name(element.tag),
        "attributes": attrs_plain(element),
        "text": normalized_text(element),
    }


def load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "id", "title", "publisher", "official_dataset_page", "upstream_repository",
        "upstream_commit", "source_url", "tei_edition", "license", "semantic_policy",
    }
    if not isinstance(value, dict) or not required <= set(value):
        missing = sorted(required - set(value) if isinstance(value, dict) else required)
        raise RuntimeError(f"invalid Hatoma manifest: missing={missing}")
    if value["upstream_commit"] != "f70a118276f5e72598dfbb0c625c2caff8f1abf2":
        raise RuntimeError("Hatoma upstream commit lock changed")
    license_spec = value.get("license") or {}
    for key in ("name", "license_file", "license_url", "attribution"):
        if not str(license_spec.get(key) or "").strip():
            raise RuntimeError(f"Hatoma license metadata missing: {key}")
    return value


def inspect_archive(archive_path: Path, manifest: dict[str, Any]) -> tuple[dict[str, Any], bytes, bytes]:
    inspections: list[dict[str, Any]] = []
    candidates: list[tuple[int, str, bytes, ET.Element]] = []
    license_members: list[tuple[str, bytes]] = []
    with zipfile.ZipFile(archive_path) as archive:
        files = [info for info in archive.infolist() if not info.is_dir()]
        for info in files:
            basename = PurePosixPath(info.filename).name
            if basename == manifest["license"]["license_file"]:
                license_members.append((info.filename, archive.read(info)))
            if PurePosixPath(info.filename).suffix.casefold() != ".xml":
                continue
            payload = archive.read(info)
            item: dict[str, Any] = {
                "member": info.filename,
                "bytes": len(payload),
                "sha256": sha256_bytes(payload),
            }
            try:
                root = ET.fromstring(payload)
            except ET.ParseError as exc:
                item.update({"parsed": False, "parse_error": str(exc), "entry_count": 0})
                inspections.append(item)
                continue
            entry_count = sum(1 for element in root.iter() if local_name(element.tag) == "entry")
            item.update({
                "parsed": True,
                "root": local_name(root.tag),
                "entry_count": entry_count,
            })
            inspections.append(item)
            if local_name(root.tag) == "TEI" and entry_count > 0:
                candidates.append((entry_count, info.filename, payload, root))

    if len(license_members) != 1:
        raise RuntimeError(f"Hatoma LICENSE.txt not unique: {[name for name, _ in license_members]}")
    license_member, license_payload = license_members[0]
    license_text = license_payload.decode("utf-8", errors="strict")
    if EXPECTED_LICENSE_TEXT not in license_text:
        raise RuntimeError("Hatoma license content is not CC BY-SA 4.0 text")
    if not candidates:
        raise RuntimeError(f"no Hatoma TEI dictionary candidate: {inspections}")
    candidates.sort(key=lambda item: item[0], reverse=True)
    max_count = candidates[0][0]
    tied = [item for item in candidates if item[0] == max_count]
    if len(tied) != 1:
        raise RuntimeError(f"Hatoma TEI candidate selection ambiguous: {[(x[0], x[1]) for x in tied]}")
    entry_count, member, payload, root = candidates[0]
    if entry_count < 15000:
        raise RuntimeError(f"Hatoma TEI entry count suspiciously low: {entry_count}")

    header_license_targets = [
        element.attrib.get("target", "")
        for element in root.iter()
        if local_name(element.tag) in {"licence", "license"}
    ]
    editions = [normalized_text(element) for element in root.iter() if local_name(element.tag) == "edition"]
    if manifest["license"]["license_url"] not in header_license_targets:
        raise RuntimeError(f"Hatoma TEI header license mismatch: {header_license_targets}")
    if manifest["tei_edition"] not in editions:
        raise RuntimeError(f"Hatoma TEI edition mismatch: {editions}")
    report = {
        "archive_members": len(files),
        "xml_inspection": inspections,
        "selected_member": member,
        "selected_xml_bytes": len(payload),
        "selected_xml_sha256": sha256_bytes(payload),
        "selected_entry_count": entry_count,
        "license_member": license_member,
        "license_bytes": len(license_payload),
        "license_sha256": sha256_bytes(license_payload),
        "tei_header_license_targets": header_license_targets,
        "tei_editions": editions,
    }
    return report, payload, license_payload


def parse_form(form: ET.Element) -> dict[str, Any]:
    orthographies = []
    pronunciations = []
    audio_refs = []
    for element in form.iter():
        name = local_name(element.tag)
        if name == "orth":
            text = normalized_text(element)
            if text:
                orthographies.append({"text": text, "attributes": attrs_plain(element)})
        elif name == "pron":
            text = normalized_text(element)
            if text:
                pronunciations.append({"text": text, "attributes": attrs_plain(element)})
        elif name == "audio":
            audio_refs.append(element_summary(element))
    return {
        "attributes": attrs_plain(form),
        "orthographies": orthographies,
        "pronunciations": pronunciations,
        "audio_refs": audio_refs,
    }


def parse_example(cit: ET.Element) -> dict[str, Any]:
    hatoma_quotes: list[dict[str, Any]] = []
    ipa: list[dict[str, Any]] = []
    translations: list[dict[str, Any]] = []
    for child in list(cit):
        name = local_name(child.tag)
        if name == "quote":
            text = normalized_text(child)
            if text:
                hatoma_quotes.append({"text": text, "attributes": attrs_plain(child)})
        elif name == "pron":
            text = normalized_text(child)
            if text:
                ipa.append({"text": text, "attributes": attrs_plain(child)})
        elif name == "cit" and child.attrib.get("type") == "translation":
            quotes = [
                {"text": normalized_text(q), "attributes": attrs_plain(q)}
                for q in descendants(child, "quote")
                if normalized_text(q)
            ]
            translations.extend(quotes)
    return {
        "attributes": attrs_plain(cit),
        "hatoma_quotes": hatoma_quotes,
        "pronunciations": ipa,
        "japanese_translations": translations,
    }


def parse_sense(sense: ET.Element, index: int) -> dict[str, Any]:
    definitions = [
        {"text": normalized_text(element), "attributes": attrs_plain(element)}
        for element in descendants(sense, "def")
        if normalized_text(element)
    ]
    usages = [element_summary(element) for element in descendants(sense, "usg") if normalized_text(element)]
    grams = [element_summary(element) for element in descendants(sense, "gram") if normalized_text(element)]
    examples = [
        parse_example(element)
        for element in descendants(sense, "cit")
        if element.attrib.get("type") == "example"
    ]
    return {
        "sense_index": index,
        "sense_id": sense.attrib.get(XML_ID, ""),
        "attributes": attrs_plain(sense),
        "definitions": definitions,
        "usages": usages,
        "grammatical_labels": grams,
        "examples": examples,
    }


def normalize(
    archive_path: Path,
    output_root: Path,
    report_path: Path,
    lock_path: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    archive_sha = sha256_file(archive_path)
    inspection, xml_payload, license_payload = inspect_archive(archive_path, manifest)
    root = ET.fromstring(xml_payload)

    source_root = output_root / "source"
    reference_root = output_root / "reference"
    preserved_root = output_root / "preserved"
    unresolved_root = output_root / "unresolved"
    for directory in (source_root, reference_root, preserved_root, unresolved_root):
        directory.mkdir(parents=True, exist_ok=True)
    selected_xml_path = source_root / "hatoma-tei-source.xml"
    license_path = source_root / "LICENSE.txt"
    selected_xml_path.write_bytes(xml_payload)
    license_path.write_bytes(license_payload)

    reference_path = reference_root / "hatoma-dictionary.jsonl"
    preserved_path = preserved_root / "hatoma-entry-subtrees.jsonl"
    unresolved_path = unresolved_root / "hatoma-missing-definition.jsonl"

    entries = [element for element in root.iter() if local_name(element.tag) == "entry"]
    normalized_records = 0
    preserved_records = 0
    meaning_complete_records = 0
    unresolved_entries = 0
    sense_count = 0
    definition_count = 0
    senses_missing_definition = 0
    example_count = 0
    example_translation_count = 0
    form_count = 0
    orthography_count = 0
    pronunciation_count = 0
    audio_ref_count = 0
    pos_counts: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter(local_name(element.tag) for element in root.iter())

    with (
        reference_path.open("w", encoding="utf-8", newline="\n") as reference,
        preserved_path.open("w", encoding="utf-8", newline="\n") as preserved,
        unresolved_path.open("w", encoding="utf-8", newline="\n") as unresolved,
    ):
        for entry_index, entry in enumerate(entries, 1):
            entry_xml = ET.tostring(entry, encoding="utf-8")
            entry_sha = sha256_bytes(entry_xml)
            entry_id = entry.attrib.get(XML_ID, "") or f"ENTRY-{entry_index:06d}"
            forms = [parse_form(form) for form in direct_children(entry, "form")]
            form_count += len(forms)
            orthography_count += sum(len(item["orthographies"]) for item in forms)
            pronunciation_count += sum(len(item["pronunciations"]) for item in forms)
            audio_ref_count += sum(len(item["audio_refs"]) for item in forms)
            surfaces = [
                item["text"]
                for form in forms
                for item in form["orthographies"]
                if item["text"]
            ]

            senses = [parse_sense(sense, idx) for idx, sense in enumerate(direct_children(entry, "sense"), 1)]
            if not senses:
                # Some TEI dictionaries nest senses. Preserve that structure rather than losing it.
                sense_elements = descendants(entry, "sense")
                senses = [parse_sense(sense, idx) for idx, sense in enumerate(sense_elements, 1)]
            sense_count += len(senses)
            entry_definitions = [definition for sense in senses for definition in sense["definitions"]]
            definition_count += len(entry_definitions)
            missing_sense_indexes = [sense["sense_index"] for sense in senses if not sense["definitions"]]
            senses_missing_definition += len(missing_sense_indexes)
            entry_examples = [example for sense in senses for example in sense["examples"]]
            example_count += len(entry_examples)
            example_translation_count += sum(len(example["japanese_translations"]) for example in entry_examples)

            entry_grams = []
            for gramgrp in direct_children(entry, "gramGrp"):
                for gram in descendants(gramgrp, "gram"):
                    text = normalized_text(gram)
                    if text:
                        entry_grams.append({"text": text, "attributes": attrs_plain(gram)})
                        pos_counts[text] += 1
            notes = [element_summary(note) for note in direct_children(entry, "note")]
            complete = bool(senses) and not missing_sense_indexes and bool(entry_definitions)
            if complete:
                meaning_complete_records += 1
            else:
                unresolved_entries += 1
                unresolved.write(json.dumps({
                    "entry_id": entry_id,
                    "entry_index": entry_index,
                    "surfaces": surfaces,
                    "sense_count": len(senses),
                    "definition_count": len(entry_definitions),
                    "senses_missing_definition": missing_sense_indexes,
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
                "forms": forms,
                "grammatical_labels": entry_grams,
                "senses": senses,
                "meanings": [item["text"] for item in entry_definitions],
                "meaning_complete": complete,
                "notes": notes,
                "source_entry_xml_sha256": entry_sha,
                "source": {
                    "dataset": manifest["title"],
                    "publisher": manifest["publisher"],
                    "official_dataset_page": manifest["official_dataset_page"],
                    "upstream_repository": manifest["upstream_repository"],
                    "upstream_commit": manifest["upstream_commit"],
                    "source_archive_sha256": archive_sha,
                    "source_xml_sha256": inspection["selected_xml_sha256"],
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

    if len(entries) != normalized_records or len(entries) != preserved_records:
        raise RuntimeError(
            f"Hatoma entry loss: source={len(entries)} normalized={normalized_records} preserved={preserved_records}"
        )

    output_files = []
    for path in (selected_xml_path, license_path, reference_path, preserved_path, unresolved_path):
        output_files.append({"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)})

    report = {
        "schema_version": manifest["schema_version"],
        "status": "NORMALIZED",
        "source_id": manifest["id"],
        "upstream_commit": manifest["upstream_commit"],
        "source_archive_bytes": archive_path.stat().st_size,
        "source_archive_sha256": archive_sha,
        **inspection,
        "entries": len(entries),
        "normalized_records": normalized_records,
        "preserved_records": preserved_records,
        "meaning_complete_records": meaning_complete_records,
        "unresolved_entries": unresolved_entries,
        "sense_count": sense_count,
        "definition_count": definition_count,
        "senses_missing_definition": senses_missing_definition,
        "example_count": example_count,
        "example_translation_count": example_translation_count,
        "form_count": form_count,
        "orthography_count": orthography_count,
        "pronunciation_count": pronunciation_count,
        "audio_reference_count": audio_ref_count,
        "pos_counts": dict(sorted(pos_counts.items())),
        "element_tag_counts": dict(sorted(tag_counts.items())),
        "output_files": output_files,
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
        "selected_member": inspection["selected_member"],
        "selected_xml_sha256": inspection["selected_xml_sha256"],
        "license_sha256": inspection["license_sha256"],
        "entries": len(entries),
        "outputs": output_files,
        "license": manifest["license"],
        "lock_state": "fixed-upstream-commit-and-computed-content-digests",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lock_path.write_text(json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def self_test() -> dict[str, Any]:
    manifest = {
        "schema_version": "1.0.0",
        "id": "test-hatoma",
        "title": "test",
        "publisher": "NINJAL",
        "official_dataset_page": "https://example.invalid",
        "upstream_repository": "https://github.com/example/test",
        "upstream_commit": "f70a118276f5e72598dfbb0c625c2caff8f1abf2",
        "source_url": "https://example.invalid/source.zip",
        "tei_edition": "20260428",
        "license": {"name": "CC BY-SA 4.0", "license_file": "LICENSE.txt", "license_url": "https://creativecommons.org/licenses/by-sa/4.0/", "attribution": "test"},
        "semantic_policy": {},
    }
    entries = []
    for index in range(15000):
        definition = "" if index == 14999 else f"意味{index}"
        entries.append(
            f'<entry xml:id="E{index}"><form><orth xml:lang="rys-x-hatoma">ア{index}</orth><pron notation="IPA">a</pron></form><gramGrp><gram>名</gram></gramGrp><sense xml:id="S{index}"><def xml:lang="ja">{definition}</def><cit type="example"><quote>例</quote><cit type="translation"><quote xml:lang="ja">訳</quote></cit></cit></sense></entry>'
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?><TEI xmlns="http://www.tei-c.org/ns/1.0">'
        '<teiHeader><fileDesc><editionStmt><edition>20260428</edition></editionStmt>'
        '<publicationStmt><availability><licence target="https://creativecommons.org/licenses/by-sa/4.0/"/></availability></publicationStmt></fileDesc></teiHeader>'
        '<text><body>' + "".join(entries) + '</body></text></TEI>'
    ).encode("utf-8")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        archive_path = root / "source.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("repo/tei/hatoma.xml", xml)
            archive.writestr("repo/LICENSE.txt", EXPECTED_LICENSE_TEXT + "\n")
        report = normalize(archive_path, root / "out", root / "report.json", root / "lock.json", manifest)
        if report["entries"] != 15000 or report["normalized_records"] != 15000 or report["preserved_records"] != 15000:
            raise RuntimeError(f"Hatoma self-test entry loss: {report}")
        if report["unresolved_entries"] != 1:
            raise RuntimeError(f"Hatoma self-test unresolved mismatch: {report['unresolved_entries']}")
        return {"status": "PASS", "entries": 15000, "unresolved": 1}


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
    manifest = load_manifest(args.manifest)
    report = normalize(args.archive, args.output_root, args.report, args.lock, manifest)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
