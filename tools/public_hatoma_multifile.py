#!/usr/bin/env python3
"""Normalize every TEI member in the fixed Hatoma dictionary repository snapshot.

The upstream repository stores the dictionary across many TEI XML files. This
runner inspects every XML member, fails closed on malformed XML, includes every
TEI document containing at least one <entry>, preserves per-member SHA-256 and
per-entry serialized XML, and emits one normalized record per source entry.
Only source <def> text is treated as lexical meaning evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import tempfile
from typing import Any
import xml.etree.ElementTree as ET
import zipfile

import public_hatoma_sources as base

EXPECTED_LICENSE_TEXT = "Attribution-ShareAlike 4.0 International"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return base.sha256_file(path)


def inspect_all_xml(
    archive_path: Path, manifest: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[tuple[str, bytes, ET.Element]], bytes, str]:
    inspections: list[dict[str, Any]] = []
    candidates: list[tuple[str, bytes, ET.Element]] = []
    license_members: list[tuple[str, bytes]] = []
    edition_values: set[str] = set()
    license_targets: set[str] = set()

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
                item.update({"parsed": False, "parse_error": str(exc), "root": "", "entry_count": 0})
                inspections.append(item)
                continue
            root_name = base.local_name(root.tag)
            entries = [element for element in root.iter() if base.local_name(element.tag) == "entry"]
            entry_count = len(entries)
            editions = [
                base.normalized_text(element)
                for element in root.iter()
                if base.local_name(element.tag) == "edition" and base.normalized_text(element)
            ]
            targets = [
                element.attrib.get("target", "")
                for element in root.iter()
                if base.local_name(element.tag) in {"licence", "license"}
                and element.attrib.get("target")
            ]
            edition_values.update(editions)
            license_targets.update(targets)
            item.update(
                {
                    "parsed": True,
                    "root": root_name,
                    "entry_count": entry_count,
                    "editions": editions,
                    "license_targets": targets,
                }
            )
            inspections.append(item)
            if root_name == "TEI" and entry_count > 0:
                candidates.append((info.filename, payload, root))

    parse_failures = [item for item in inspections if item.get("parsed") is False]
    if parse_failures:
        raise RuntimeError(
            f"Hatoma XML parse failure: count={len(parse_failures)} sample={parse_failures[:10]}"
        )
    if len(license_members) != 1:
        raise RuntimeError(f"Hatoma LICENSE.txt not unique: {[name for name, _ in license_members]}")
    license_member, license_payload = license_members[0]
    license_text = license_payload.decode("utf-8", errors="strict")
    if EXPECTED_LICENSE_TEXT not in license_text:
        raise RuntimeError("Hatoma LICENSE.txt is not CC BY-SA 4.0 text")
    if not candidates:
        raise RuntimeError("no TEI entry-bearing Hatoma XML members")
    if manifest["tei_edition"] not in edition_values:
        raise RuntimeError(f"Hatoma TEI edition not observed anywhere: {sorted(edition_values)}")
    if manifest["license"]["license_url"] not in license_targets:
        raise RuntimeError(f"Hatoma TEI license target not observed anywhere: {sorted(license_targets)}")
    candidates.sort(key=lambda item: item[0])
    return inspections, candidates, license_payload, license_member


def normalize_all_members(
    archive_path: Path,
    output_root: Path,
    report_path: Path,
    lock_path: Path,
    manifest: dict[str, Any],
    *,
    minimum_entries: int = 15000,
) -> dict[str, Any]:
    archive_sha = sha256_file(archive_path)
    inspections, candidates, license_payload, license_member = inspect_all_xml(archive_path, manifest)

    source_root = output_root / "source"
    reference_root = output_root / "reference"
    preserved_root = output_root / "preserved"
    unresolved_root = output_root / "unresolved"
    for directory in (source_root, reference_root, preserved_root, unresolved_root):
        directory.mkdir(parents=True, exist_ok=True)

    license_path = source_root / "LICENSE.txt"
    member_manifest_path = source_root / "tei-members.jsonl"
    license_path.write_bytes(license_payload)
    with member_manifest_path.open("w", encoding="utf-8", newline="\n") as handle:
        for item in inspections:
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")

    reference_path = reference_root / "hatoma-dictionary.jsonl"
    preserved_path = preserved_root / "hatoma-entry-subtrees.jsonl"
    unresolved_path = unresolved_root / "hatoma-missing-definition.jsonl"

    total_entries = sum(
        sum(1 for element in root.iter() if base.local_name(element.tag) == "entry")
        for _, _, root in candidates
    )
    if total_entries < minimum_entries:
        raise RuntimeError(
            f"Hatoma aggregate TEI entry count suspiciously low: entries={total_entries} members={len(candidates)}"
        )

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
    tag_counts: Counter[str] = Counter()
    candidate_reports: list[dict[str, Any]] = []

    with (
        reference_path.open("w", encoding="utf-8", newline="\n") as reference,
        preserved_path.open("w", encoding="utf-8", newline="\n") as preserved,
        unresolved_path.open("w", encoding="utf-8", newline="\n") as unresolved,
    ):
        global_entry_index = 0
        for member_name, member_payload, root in candidates:
            member_sha = sha256_bytes(member_payload)
            entries = [element for element in root.iter() if base.local_name(element.tag) == "entry"]
            candidate_reports.append(
                {
                    "member": member_name,
                    "bytes": len(member_payload),
                    "sha256": member_sha,
                    "entry_count": len(entries),
                }
            )
            tag_counts.update(base.local_name(element.tag) for element in root.iter())
            for member_entry_index, entry in enumerate(entries, 1):
                global_entry_index += 1
                entry_xml = ET.tostring(entry, encoding="utf-8")
                entry_sha = sha256_bytes(entry_xml)
                source_entry_id = entry.attrib.get(base.XML_ID, "")
                entry_id = source_entry_id or f"{PurePosixPath(member_name).stem}:{member_entry_index:03d}"

                forms = [base.parse_form(form) for form in base.direct_children(entry, "form")]
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

                direct_senses = base.direct_children(entry, "sense")
                sense_elements = direct_senses or base.descendants(entry, "sense")
                senses = [base.parse_sense(sense, idx) for idx, sense in enumerate(sense_elements, 1)]
                sense_count += len(senses)
                definitions = [definition for sense in senses for definition in sense["definitions"]]
                definition_count += len(definitions)
                missing_sense_indexes = [sense["sense_index"] for sense in senses if not sense["definitions"]]
                senses_missing_definition += len(missing_sense_indexes)
                examples = [example for sense in senses for example in sense["examples"]]
                example_count += len(examples)
                example_translation_count += sum(len(example["japanese_translations"]) for example in examples)

                entry_grams: list[dict[str, Any]] = []
                for gramgrp in base.direct_children(entry, "gramGrp"):
                    for gram in base.descendants(gramgrp, "gram"):
                        text = base.normalized_text(gram)
                        if text:
                            entry_grams.append({"text": text, "attributes": base.attrs_plain(gram)})
                            pos_counts[text] += 1
                notes = [base.element_summary(note) for note in base.direct_children(entry, "note")]
                complete = bool(senses) and not missing_sense_indexes and bool(definitions)
                if complete:
                    meaning_complete_records += 1
                else:
                    unresolved_entries += 1
                    unresolved.write(
                        json.dumps(
                            {
                                "archive_member": member_name,
                                "source_member_sha256": member_sha,
                                "entry_id": entry_id,
                                "global_entry_index": global_entry_index,
                                "member_entry_index": member_entry_index,
                                "surfaces": surfaces,
                                "sense_count": len(senses),
                                "definition_count": len(definitions),
                                "senses_missing_definition": missing_sense_indexes,
                                "source_entry_xml_sha256": entry_sha,
                                "reason": "HATOMA_DEFINITION_INCOMPLETE",
                                "review_status": "needs-evidence",
                                "runtime_eligible": False,
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n"
                    )

                preserved.write(
                    json.dumps(
                        {
                            "archive_member": member_name,
                            "source_member_sha256": member_sha,
                            "entry_id": entry_id,
                            "global_entry_index": global_entry_index,
                            "member_entry_index": member_entry_index,
                            "source_entry_xml_sha256": entry_sha,
                            "entry_xml": entry_xml.decode("utf-8"),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
                preserved_records += 1

                reference.write(
                    json.dumps(
                        {
                            "record_id": f"{manifest['id']}:{member_name}:{entry_id}",
                            "archive_member": member_name,
                            "source_member_sha256": member_sha,
                            "global_entry_index": global_entry_index,
                            "member_entry_index": member_entry_index,
                            "entry_id": entry_id,
                            "surfaces": surfaces,
                            "forms": forms,
                            "grammatical_labels": entry_grams,
                            "senses": senses,
                            "meanings": [item["text"] for item in definitions],
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
                                "license": manifest["license"]["name"],
                                "license_url": manifest["license"]["license_url"],
                                "attribution": manifest["license"]["attribution"],
                                "tei_edition": manifest["tei_edition"],
                            },
                            "evidence_status": "reference_only",
                            "runtime_eligible": False,
                            "llm_generated": False,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
                normalized_records += 1

    if total_entries != normalized_records or total_entries != preserved_records:
        raise RuntimeError(
            f"Hatoma entry loss: source={total_entries} normalized={normalized_records} preserved={preserved_records}"
        )

    output_files = []
    for path in (license_path, member_manifest_path, reference_path, preserved_path, unresolved_path):
        output_files.append({"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)})

    report = {
        "schema_version": manifest["schema_version"],
        "status": "NORMALIZED",
        "source_id": manifest["id"],
        "upstream_commit": manifest["upstream_commit"],
        "source_archive_bytes": archive_path.stat().st_size,
        "source_archive_sha256": archive_sha,
        "xml_members_inspected": len(inspections),
        "tei_entry_members": len(candidates),
        "tei_member_records": candidate_reports,
        "license_member": license_member,
        "license_bytes": len(license_payload),
        "license_sha256": sha256_bytes(license_payload),
        "entries": total_entries,
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
    member_lock_sha = sha256_file(member_manifest_path)
    lock = {
        "source_id": manifest["id"],
        "upstream_commit": manifest["upstream_commit"],
        "source_url": manifest["source_url"],
        "source_archive_sha256": archive_sha,
        "xml_members_inspected": len(inspections),
        "tei_entry_members": len(candidates),
        "tei_members_manifest_sha256": member_lock_sha,
        "license_sha256": sha256_bytes(license_payload),
        "entries": total_entries,
        "outputs": output_files,
        "license": manifest["license"],
        "lock_state": "fixed-upstream-commit-all-tei-members-and-computed-content-digests",
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
        "license": {
            "name": "CC BY-SA 4.0",
            "license_file": "LICENSE.txt",
            "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
            "attribution": "test",
        },
        "semantic_policy": {},
    }
    header = (
        '<teiHeader><fileDesc><editionStmt><edition>20260428</edition></editionStmt>'
        '<publicationStmt><availability><licence target="https://creativecommons.org/licenses/by-sa/4.0/"/>'
        '</availability></publicationStmt></fileDesc></teiHeader>'
    )
    def doc(entry_id: str, definition: str) -> bytes:
        return (
            '<?xml version="1.0" encoding="UTF-8"?><TEI xmlns="http://www.tei-c.org/ns/1.0">'
            + header
            + f'<text><body><entry xml:id="{entry_id}"><form><orth>語{entry_id}</orth></form>'
            + f'<sense><def xml:lang="ja">{definition}</def></sense></entry></body></text></TEI>'
        ).encode("utf-8")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        archive_path = root / "source.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("repo/a.xml", doc("A", "意味A"))
            archive.writestr("repo/b.xml", doc("B", ""))
            archive.writestr("repo/LICENSE.txt", EXPECTED_LICENSE_TEXT + "\n")
        report = normalize_all_members(
            archive_path,
            root / "out",
            root / "report.json",
            root / "lock.json",
            manifest,
            minimum_entries=2,
        )
        if report["entries"] != 2 or report["tei_entry_members"] != 2 or report["unresolved_entries"] != 1:
            raise RuntimeError(f"Hatoma multifile self-test failed: {report}")
        return {"status": "PASS", "entries": 2, "tei_members": 2, "unresolved": 1}


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
    report = normalize_all_members(args.archive, args.output_root, args.report, args.lock, manifest)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
