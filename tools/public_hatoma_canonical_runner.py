#!/usr/bin/env python3
"""Canonical Hatoma TEI runner with explicit structural-entry classification.

Uses the source-locking/TEI helper functions in public_hatoma_multifile.py, but
classifies the 105 parent entries that contain child <entry> records and no direct
<sense> as structural entry groups rather than missing-meaning lexical records.
Only four lexical entries with source-empty <def> remain needs-evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

import public_hatoma_multifile as h

EXPECTED = {
    "total_entries": 16946,
    "structural_entries": 105,
    "structural_child_references": 214,
    "lexical_entries": 16841,
    "lexical_meaning_complete_records": 16837,
    "unresolved_lexical_entries": 4,
    "sense_records": 18327,
    "definition_elements": 18346,
    "nonempty_definitions": 18342,
    "empty_definitions": 4,
    "example_records": 34155,
    "translation_records": 34155,
    "form_records": 16732,
    "orthography_records": 16732,
    "media_reference_records": 16732,
}


def child_entry_ids(entry: ET.Element) -> list[str]:
    return [
        child.attrib.get(h.base.XML_ID, "")
        for child in h.direct(entry, "entry")
    ]


def normalize(
    archive_path: Path,
    output_root: Path,
    report_path: Path,
    lock_path: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    inspections, member, payload, root, license_member, license_payload = h.inspect_archive(
        archive_path, manifest
    )
    archive_sha = h.sha256_file(archive_path)
    canonical_sha = h.sha256_bytes(payload)
    license_sha = h.sha256_bytes(license_payload)

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
            handle.write(
                json.dumps(
                    {
                        **item,
                        "disposition": (
                            "canonical_data_source"
                            if item["canonical"]
                            else "inventory_only_not_normalized"
                        ),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )

    reference_path = reference_root / "hatoma-dictionary.jsonl"
    preserved_path = preserved_root / "hatoma-entry-subtrees.jsonl"
    unresolved_path = unresolved_root / "hatoma-missing-definition.jsonl"

    entries = [element for element in root.iter() if h.local(element.tag) == "entry"]
    source_counts = Counter(h.local(element.tag) for element in root.iter())

    total_entries = 0
    structural_entries = 0
    structural_child_references = 0
    lexical_entries = 0
    lexical_meaning_complete_records = 0
    unresolved_lexical_entries = 0
    sense_records = 0
    definition_elements = 0
    nonempty_definitions = 0
    empty_definitions = 0
    example_records = 0
    translation_records = 0
    form_records = 0
    orthography_records = 0
    media_reference_records = 0
    preserved_records = 0
    normalized_records = 0
    pos_counts: Counter[str] = Counter()

    with (
        reference_path.open("w", encoding="utf-8", newline="\n") as reference,
        preserved_path.open("w", encoding="utf-8", newline="\n") as preserved,
        unresolved_path.open("w", encoding="utf-8", newline="\n") as unresolved,
    ):
        for entry_index, entry in enumerate(entries, 1):
            total_entries += 1
            entry_xml = ET.tostring(entry, encoding="utf-8")
            entry_sha = h.sha256_bytes(entry_xml)
            entry_id = entry.attrib.get(h.base.XML_ID, "") or f"ENTRY-{entry_index:06d}"

            forms = [h.parse_form(form) for form in h.direct(entry, "form")]
            form_records += len(forms)
            orthography_records += sum(len(item["orthographies"]) for item in forms)
            media_reference_records += sum(len(item["media_refs"]) for item in forms)
            surfaces = [
                orth["text"]
                for form in forms
                for orth in form["orthographies"]
                if orth["text"]
            ]

            direct_senses = h.direct(entry, "sense")
            children = child_entry_ids(entry)
            structural = not direct_senses and bool(children)
            if not direct_senses and not children:
                raise RuntimeError(
                    f"Hatoma entry has neither direct sense nor child entry: {entry_id}"
                )

            parsed_senses = [
                h.parse_sense(sense, index)
                for index, sense in enumerate(direct_senses, 1)
            ]
            sense_records += len(parsed_senses)
            defs = [item for sense in parsed_senses for item in sense["definitions"]]
            nonempty_defs = [
                item
                for sense in parsed_senses
                for item in sense["nonempty_definitions"]
            ]
            definition_elements += len(defs)
            nonempty_definitions += len(nonempty_defs)
            empty_definitions += sum(1 for item in defs if not item["text"])
            example_records += sum(len(sense["examples"]) for sense in parsed_senses)
            translation_records += sum(
                len(example["translations"])
                for sense in parsed_senses
                for example in sense["examples"]
            )

            for sense in parsed_senses:
                for gram in sense["grammatical_labels"]:
                    pos_counts[gram["text"]] += 1
            for gramgrp in h.direct(entry, "gramGrp"):
                for gram in gramgrp.iter():
                    if h.local(gram.tag) == "gram":
                        value = h.text(gram)
                        if value:
                            pos_counts[value] += 1

            if structural:
                structural_entries += 1
                structural_child_references += len(children)
                record_type = "entry_group"
                meaning_required = False
                meaning_complete = None
                semantic_complete = True
                review_status = "source-structural"
            else:
                lexical_entries += 1
                record_type = "lexical_entry"
                meaning_required = True
                missing_senses = [
                    sense["sense_index"]
                    for sense in parsed_senses
                    if not sense["meaning_complete"]
                ]
                meaning_complete = (
                    bool(parsed_senses)
                    and not missing_senses
                    and bool(nonempty_defs)
                )
                semantic_complete = bool(meaning_complete)
                review_status = (
                    "reference-only" if meaning_complete else "needs-evidence"
                )
                if meaning_complete:
                    lexical_meaning_complete_records += 1
                else:
                    unresolved_lexical_entries += 1
                    unresolved.write(
                        json.dumps(
                            {
                                "entry_id": entry_id,
                                "entry_index": entry_index,
                                "surfaces": surfaces,
                                "sense_count": len(parsed_senses),
                                "definition_count": len(defs),
                                "nonempty_definition_count": len(nonempty_defs),
                                "senses_missing_definition": missing_senses,
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
                        "entry_id": entry_id,
                        "entry_index": entry_index,
                        "record_type": record_type,
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
                        "record_id": f"{manifest['id']}:{entry_id}",
                        "entry_index": entry_index,
                        "entry_id": entry_id,
                        "record_type": record_type,
                        "meaning_required": meaning_required,
                        "meaning_complete": meaning_complete,
                        "semantic_complete": semantic_complete,
                        "review_status": review_status,
                        "child_entry_ids": children,
                        "surfaces": surfaces,
                        "forms": forms,
                        "senses": parsed_senses,
                        "meanings": [item["text"] for item in nonempty_defs],
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

    observed = {
        "total_entries": total_entries,
        "structural_entries": structural_entries,
        "structural_child_references": structural_child_references,
        "lexical_entries": lexical_entries,
        "lexical_meaning_complete_records": lexical_meaning_complete_records,
        "unresolved_lexical_entries": unresolved_lexical_entries,
        "sense_records": sense_records,
        "definition_elements": definition_elements,
        "nonempty_definitions": nonempty_definitions,
        "empty_definitions": empty_definitions,
        "example_records": example_records,
        "translation_records": translation_records,
        "form_records": form_records,
        "orthography_records": orthography_records,
        "media_reference_records": media_reference_records,
    }
    if observed != EXPECTED:
        raise RuntimeError(
            f"Hatoma canonical semantic classification mismatch: observed={observed} expected={EXPECTED}"
        )
    if normalized_records != total_entries or preserved_records != total_entries:
        raise RuntimeError(
            f"Hatoma entry loss: total={total_entries} normalized={normalized_records} preserved={preserved_records}"
        )
    if lexical_entries != lexical_meaning_complete_records + unresolved_lexical_entries:
        raise RuntimeError("Hatoma lexical completeness accounting mismatch")

    outputs = []
    for path in (
        canonical_path,
        license_path,
        inventory_path,
        reference_path,
        preserved_path,
        unresolved_path,
    ):
        outputs.append(
            {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": h.sha256_file(path),
            }
        )

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
        "normalized_records": normalized_records,
        "preserved_records": preserved_records,
        **observed,
        "semantic_complete_records": structural_entries + lexical_meaning_complete_records,
        "meaning_policy": (
            "Structural entry groups do not require lexical definitions and keep child_entry_ids. "
            "Lexical entries require source <def>; four source-empty definitions remain needs-evidence."
        ),
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
        "entries": total_entries,
        "structural_entries": structural_entries,
        "lexical_entries": lexical_entries,
        "inventory_sha256": h.sha256_file(inventory_path),
        "outputs": outputs,
        "license": manifest["license"],
        "lock_state": "fixed-commit-canonical-tei-semantic-record-types-and-digests",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lock_path.write_text(
        json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def self_test() -> dict[str, Any]:
    group = ET.fromstring(
        '<entry xmlns="http://www.tei-c.org/ns/1.0" xml:id="G">'
        '<form><orth>同形</orth></form>'
        '<entry xml:id="G.1"><sense><def>意味1</def></sense></entry>'
        '<entry xml:id="G.2"><sense><def>意味2</def></sense></entry>'
        '</entry>'
    )
    lexical = ET.fromstring(
        '<entry xmlns="http://www.tei-c.org/ns/1.0" xml:id="L">'
        '<form><orth>語</orth></form><sense><def>意味</def></sense></entry>'
    )
    if len(child_entry_ids(group)) != 2 or h.direct(group, "sense"):
        raise RuntimeError("Hatoma group-entry self-test failed")
    senses = [h.parse_sense(s, i) for i, s in enumerate(h.direct(lexical, "sense"), 1)]
    if len(senses) != 1 or senses[0]["nonempty_definitions"][0]["text"] != "意味":
        raise RuntimeError("Hatoma lexical-entry self-test failed")
    return {"status": "PASS", "structural_children": 2, "lexical_senses": 1}


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
    if any(
        value is None
        for value in (
            args.manifest,
            args.archive,
            args.output_root,
            args.report,
            args.lock,
        )
    ):
        parser.error("--manifest --archive --output-root --report --lock are required")
    manifest = h.base.load_manifest(args.manifest)
    report = normalize(
        args.archive, args.output_root, args.report, args.lock, manifest
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
