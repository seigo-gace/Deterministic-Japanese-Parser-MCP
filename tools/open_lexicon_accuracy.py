#!/usr/bin/env python3
"""Audit a built JMdict lexical snapshot for fidelity, recall and precision."""
from __future__ import annotations

import argparse
from collections import defaultdict
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

# Load the standalone canonical matcher without importing the package __init__.
# This keeps the source-fidelity audit independent from runtime dependencies and
# allows it to run before wheel/dependency installation in Release Readiness.
_CANONICAL_PATH = ROOT / "src/deterministic_japanese_parser_mcp/canonical.py"
_CANONICAL_SPEC = importlib.util.spec_from_file_location(
    "djpmcp_open_lexicon_accuracy_canonical",
    _CANONICAL_PATH,
)
if _CANONICAL_SPEC is None or _CANONICAL_SPEC.loader is None:
    raise RuntimeError(f"cannot load canonical matcher: {_CANONICAL_PATH}")
_CANONICAL_MODULE = importlib.util.module_from_spec(_CANONICAL_SPEC)
_CANONICAL_SPEC.loader.exec_module(_CANONICAL_MODULE)
Canonicalizer = _CANONICAL_MODULE.Canonicalizer

from dictionary_supply.common import LexiconRecord, read_jsonl, sha256_file


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    return re.sub(r"\s+", " ", value).strip()


def unique(values) -> list[str]:
    output: list[str] = []
    for value in values:
        item = normalize(str(value))
        if item and item not in output:
            output.append(item)
    return output


def texts(element: ET.Element, tag: str) -> list[str]:
    return unique(item.text or "" for item in element.findall(tag))


def source_expectation(entry: ET.Element) -> dict | None:
    source_id = normalize(entry.findtext("ent_seq") or "")
    writings = texts(entry, "k_ele/keb")
    reading_mappings: list[dict] = []
    for reading_element in entry.findall("r_ele"):
        reading = normalize(reading_element.findtext("reb") or "")
        if not reading:
            continue
        reading_mappings.append({
            "reading": reading,
            "restricted_to": texts(reading_element, "re_restr"),
            "no_kanji": reading_element.find("re_nokanji") is not None,
        })
    readings = unique(item["reading"] for item in reading_mappings)
    candidates = writings or readings
    if not source_id or not candidates:
        return None

    part_of_speech: list[str] = []
    domains: list[str] = []
    usage_labels: list[str] = []
    for sense in entry.findall("sense"):
        part_of_speech = unique([*part_of_speech, *texts(sense, "pos")])
        domains = unique([*domains, *texts(sense, "field")])
        usage_labels = unique([
            *usage_labels,
            *texts(sense, "misc"),
            *texts(sense, "dial"),
        ])
    lemma = candidates[0]
    return {
        "source_id": source_id,
        "lemma": lemma,
        "surfaces": unique([lemma, *writings]),
        "readings": readings,
        "reading_mappings": reading_mappings,
        "part_of_speech": part_of_speech,
        "domains": domains,
        "usage_labels": usage_labels,
    }


def lexicon_paths(root: Path) -> list[Path]:
    return sorted([
        *root.rglob("*.jsonl"),
        *root.rglob("*.jsonl.gz"),
    ], key=lambda item: str(item))


def load_runtime_records(root: Path) -> list[LexiconRecord]:
    records: list[LexiconRecord] = []
    for path in lexicon_paths(root):
        records.extend(read_jsonl(path))
    return records


def compare_record(
    record: LexiconRecord,
    expected: dict,
    *,
    source_sha256: str,
) -> list[str]:
    errors: list[str] = []
    checks = {
        "lemma": record.lemma,
        "surfaces": record.surfaces,
        "readings": record.readings,
        "reading_mappings": record.reading_mappings,
        "part_of_speech": record.part_of_speech,
        "domains": record.domains,
        "usage_labels": record.usage_labels,
    }
    for key, actual in checks.items():
        if actual != expected[key]:
            errors.append(
                f"{record.record_id}: {key} mismatch: "
                f"expected={expected[key]!r} actual={actual!r}"
            )
    if record.source.dataset != "JMdict":
        errors.append(
            f"{record.record_id}: unexpected dataset={record.source.dataset}"
        )
    if record.source.source_id != expected["source_id"]:
        errors.append(
            f"{record.record_id}: source_id mismatch: "
            f"expected={expected['source_id']} actual={record.source.source_id}"
        )
    if record.source.source_sha256 != source_sha256:
        errors.append(f"{record.record_id}: source SHA mismatch")
    if record.review_status != "approved":
        errors.append(
            f"{record.record_id}: review_status={record.review_status}"
        )
    for field_name in ("senses", "synonyms", "antonyms", "related", "forms"):
        if getattr(record, field_name):
            errors.append(
                f"{record.record_id}: semantic field was auto-promoted: {field_name}"
            )
    writing_set = set(expected["surfaces"])
    for reading in record.readings:
        if reading in record.surfaces and reading not in writing_set:
            errors.append(
                f"{record.record_id}: reading was promoted as an alias: {reading}"
            )
    return errors


def load_source_matches(
    source: Path,
    source_ids: set[str],
) -> dict[str, dict]:
    found: dict[str, dict] = {}
    opener = gzip.open if source.name.endswith(".gz") else open
    with opener(source, "rb") as handle:
        for _, element in ET.iterparse(handle, events=("end",)):
            if element.tag != "entry":
                continue
            source_id = normalize(element.findtext("ent_seq") or "")
            if source_id in source_ids:
                expected = source_expectation(element)
                if expected is not None:
                    found[source_id] = expected
            element.clear()
            if len(found) == len(source_ids):
                break
    return found


def stable_surface_order(values: set[str]) -> list[str]:
    return sorted(
        values,
        key=lambda value: hashlib.sha256(value.encode("utf-8")).digest(),
    )


def containment_cases(
    owners: dict[str, set[str]],
    *,
    limit: int,
) -> list[tuple[str, str]]:
    surfaces = set(owners)
    output: list[tuple[str, str]] = []
    for longer in stable_surface_order(surfaces):
        if len(longer) < 2 or len(longer) > 32:
            continue
        maximum_part = min(12, len(longer) - 1)
        for size in range(1, maximum_part + 1):
            for start in range(0, len(longer) - size + 1):
                shorter = longer[start : start + size]
                if shorter == longer or shorter not in surfaces:
                    continue
                if owners[shorter].intersection(owners[longer]):
                    continue
                output.append((shorter, longer))
                if len(output) >= limit:
                    return output
    return output


def audit(
    *,
    source: Path,
    lexicon_root: Path,
    manifest_path: Path,
    minimum_records: int,
    containment_limit: int,
    pollution_limit: int,
) -> tuple[dict, list[str]]:
    errors: list[str] = []
    records = load_runtime_records(lexicon_root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_digest = sha256_file(source)

    if len(records) < minimum_records:
        errors.append(
            f"minimum record contract failed: required={minimum_records} "
            f"actual={len(records)}"
        )
    if manifest.get("record_count") != len(records):
        errors.append(
            "manifest/runtime count mismatch: "
            f"manifest={manifest.get('record_count')} runtime={len(records)}"
        )
    if manifest.get("reading_alias_promotion") is not False:
        errors.append("manifest must declare reading_alias_promotion=false")

    by_source_id: dict[str, LexiconRecord] = {}
    for record in records:
        source_id = record.source.source_id
        if source_id in by_source_id:
            errors.append(f"duplicate source_id in runtime pack: {source_id}")
        by_source_id[source_id] = record
    expected_by_source = load_source_matches(source, set(by_source_id))
    missing_source_ids = sorted(set(by_source_id) - set(expected_by_source))
    if missing_source_ids:
        errors.append(
            f"runtime records missing from source: {missing_source_ids[:20]}"
        )

    fidelity_records = 0
    for source_id, record in by_source_id.items():
        expected = expected_by_source.get(source_id)
        if expected is None:
            continue
        record_errors = compare_record(
            record,
            expected,
            source_sha256=source_digest,
        )
        if record_errors:
            errors.extend(record_errors[:20])
        else:
            fidelity_records += 1
        if len(errors) >= 100:
            break

    groups: dict[str, list[str]] = defaultdict(list)
    owners: dict[str, set[str]] = defaultdict(set)
    for record in records:
        for surface in unique([record.lemma, *record.surfaces]):
            if surface not in groups[record.lemma]:
                groups[record.lemma].append(surface)
            owners[surface].add(record.lemma)
    canonicalizer = Canonicalizer({
        "groups": dict(groups),
        "exact_only_groups": sorted(groups),
    })

    exact_surface_checks = 0
    ambiguous_surface_checks = 0
    for surface, expected_owners in owners.items():
        expected_ids = frozenset(sorted(expected_owners))
        if canonicalizer.exact_ids(surface) != expected_ids:
            errors.append(
                f"exact lookup mismatch: {surface!r}: "
                f"expected={sorted(expected_ids)} "
                f"actual={sorted(canonicalizer.exact_ids(surface))}"
            )
        if canonicalizer.ids(surface) != expected_ids:
            errors.append(
                f"isolated lexical lookup mismatch: {surface!r}: "
                f"expected={sorted(expected_ids)} "
                f"actual={sorted(canonicalizer.ids(surface))}"
            )
        exact_surface_checks += 1
        if len(expected_ids) > 1:
            ambiguous_surface_checks += 1
        if len(errors) >= 100:
            break

    containment = containment_cases(owners, limit=containment_limit)
    containment_passed = 0
    for shorter, longer in containment:
        if canonicalizer.related(shorter, longer):
            errors.append(
                f"distinct containment false positive: {shorter!r} / {longer!r}"
            )
        else:
            containment_passed += 1
        if len(errors) >= 100:
            break

    pollution_passed = 0
    for surface in stable_surface_order(set(owners))[:pollution_limit]:
        wrapped = f"対象は「{surface}」です。"
        leaked = canonicalizer.ids(wrapped).intersection(owners[surface])
        if leaked:
            errors.append(
                f"exact-only lexical identity leaked into substring scan: "
                f"surface={surface!r} ids={sorted(leaked)}"
            )
        else:
            pollution_passed += 1
        if len(errors) >= 100:
            break

    report = {
        "schema_version": "1.0.0",
        "status": "PASS" if not errors else "FAIL",
        "source_sha256": source_digest,
        "runtime_records": len(records),
        "source_records_found": len(expected_by_source),
        "source_fidelity_records": fidelity_records,
        "exact_surface_checks": exact_surface_checks,
        "ambiguous_surface_checks": ambiguous_surface_checks,
        "containment_precision_checks": len(containment),
        "containment_precision_passed": containment_passed,
        "substring_pollution_checks": min(pollution_limit, len(owners)),
        "substring_pollution_passed": pollution_passed,
        "unique_surfaces": len(owners),
        "unique_canonical_lemmas": len(groups),
        "errors": errors[:100],
    }
    return report, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--lexicon-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--minimum-records", type=int, default=100000)
    parser.add_argument("--containment-cases", type=int, default=20000)
    parser.add_argument("--pollution-cases", type=int, default=20000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report, errors = audit(
        source=args.source,
        lexicon_root=args.lexicon_root,
        manifest_path=args.manifest,
        minimum_records=args.minimum_records,
        containment_limit=args.containment_cases,
        pollution_limit=args.pollution_cases,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
