#!/usr/bin/env python3
"""Normalize the MIT-licensed J-Ono JSON collection.

The source-authored meaning text and refer graph are preserved. A refer target is
resolved only according to the source's documented `<literal>:<def num>` syntax.
No image payload is copied; example image/source metadata remains evidence only.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

ALLOWED_TYPES = {"", "o", "v", "s", "m", "e", "c"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def as_strings(value: Any, field: str, record_id: str) -> list[str]:
    if not isinstance(value, list):
        raise RuntimeError(f"{record_id}: {field} must be list")
    output: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise RuntimeError(f"{record_id}: {field} contains non-string")
        output.append(item)
    return output


def parse_refer(value: str) -> tuple[str, int] | None:
    value = value.strip()
    if not value:
        return None
    if ":" not in value:
        raise RuntimeError(f"invalid refer syntax: {value!r}")
    target_id, index_raw = value.rsplit(":", 1)
    target_id = target_id.strip()
    if not target_id or not index_raw.isdigit():
        raise RuntimeError(f"invalid refer syntax: {value!r}")
    index = int(index_raw)
    if index < 1:
        raise RuntimeError(f"refer definition index must be 1-based positive: {value!r}")
    return target_id, index


def normalize(
    manifest_path: Path,
    data_path: Path,
    sources_path: Path,
    license_path: Path,
    output_path: Path,
    source_output_path: Path,
    report_path: Path,
    lock_path: Path,
) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    specs = [s for s in manifest.get("sources", []) if s.get("id") == "j-ono-json-collection" and s.get("status") == "enabled"]
    if len(specs) != 1:
        raise RuntimeError("J-Ono source spec is not uniquely enabled")
    spec = specs[0]
    data = load_json(data_path)
    source_records = load_json(sources_path)
    if not isinstance(data, list) or not isinstance(source_records, list):
        raise RuntimeError("J-Ono top-level JSON values must be arrays")

    license_text = license_path.read_text(encoding="utf-8-sig")
    if "MIT License" not in license_text or "JSON COLLECTION" not in license_text:
        raise RuntimeError("J-Ono JSON Collection MIT license text not recognized")

    by_id: dict[str, dict[str, Any]] = {}
    for item in data:
        if not isinstance(item, dict):
            raise RuntimeError("J-Ono definition record must be object")
        record_id = str(item.get("id") or "").strip()
        if not record_id or record_id in by_id:
            raise RuntimeError(f"J-Ono definition id invalid/duplicate: {record_id!r}")
        definitions = item.get("definition")
        if not isinstance(definitions, list) or not definitions:
            raise RuntimeError(f"J-Ono record has no definitions: {record_id}")
        by_id[record_id] = item

    source_ids: set[str] = set()
    normalized_source_records: list[dict[str, Any]] = []
    for group_index, group in enumerate(source_records, 1):
        if not isinstance(group, dict):
            raise RuntimeError(f"J-Ono source group {group_index} is not object")
        publisher = str(group.get("publisher_name") or "")
        site = str(group.get("site") or "")
        sources = group.get("sources")
        if not isinstance(sources, list):
            raise RuntimeError(f"J-Ono source group {group_index} sources not list")
        for item in sources:
            if not isinstance(item, dict):
                raise RuntimeError("J-Ono source item is not object")
            source_id = str(item.get("id") or "").strip()
            if not source_id or source_id in source_ids:
                raise RuntimeError(f"J-Ono source id invalid/duplicate: {source_id!r}")
            source_ids.add(source_id)
            normalized_source_records.append(
                {
                    "source_id": source_id,
                    "publisher_name": publisher,
                    "site": site,
                    "manga": str(item.get("manga") or ""),
                }
            )

    refer_edges: list[tuple[str, int, str, int]] = []
    type_counts: Counter[str] = Counter()
    example_count = 0
    example_source_missing: list[dict[str, Any]] = []
    local_meaning_empty = 0
    local_meaning_nonempty = 0
    definition_children = 0
    surface_variant_count = 0

    for record_id, item in by_id.items():
        romaji = as_strings(item.get("romaji", []), "romaji", record_id)
        katakana = as_strings(item.get("katakana", []), "katakana", record_id)
        hiragana = as_strings(item.get("hiragana", []), "hiragana", record_id)
        surface_variant_count += len(romaji) + len(katakana) + len(hiragana)
        for def_index, definition in enumerate(item["definition"], 1):
            if not isinstance(definition, dict):
                raise RuntimeError(f"{record_id}:{def_index} definition is not object")
            definition_children += 1
            meaning = str(definition.get("meaning") or "").strip()
            if meaning:
                local_meaning_nonempty += 1
            else:
                local_meaning_empty += 1
            type_code = str(definition.get("type") or "").strip()
            if type_code not in ALLOWED_TYPES:
                raise RuntimeError(f"{record_id}:{def_index} unknown type {type_code!r}")
            type_counts[type_code] += 1
            refer = str(definition.get("refer") or "").strip()
            parsed = parse_refer(refer)
            if parsed:
                target_id, target_index = parsed
                target = by_id.get(target_id)
                if target is None:
                    raise RuntimeError(f"{record_id}:{def_index} missing refer target {target_id!r}")
                if target_index > len(target["definition"]):
                    raise RuntimeError(
                        f"{record_id}:{def_index} refer index out of range: {refer!r}"
                    )
                refer_edges.append((record_id, def_index, target_id, target_index))
            equivalents = definition.get("equivalent", [])
            as_strings(equivalents, "equivalent", f"{record_id}:{def_index}")
            examples = definition.get("example", [])
            if not isinstance(examples, list):
                raise RuntimeError(f"{record_id}:{def_index} example must be list")
            for example_index, example in enumerate(examples, 1):
                if not isinstance(example, dict):
                    raise RuntimeError(f"{record_id}:{def_index}:{example_index} example not object")
                example_count += 1
                source_id = str(example.get("source") or "").strip()
                if source_id and source_id not in source_ids:
                    if len(example_source_missing) < 50:
                        example_source_missing.append(
                            {
                                "record_id": record_id,
                                "definition_index": def_index,
                                "example_index": example_index,
                                "source": source_id,
                            }
                        )
    if example_source_missing:
        raise RuntimeError(
            f"J-Ono example source references missing: count_at_least={len(example_source_missing)} "
            f"sample={example_source_missing[:10]}"
        )

    def resolve_meanings(record_id: str, def_index: int, trail: tuple[tuple[str, int], ...] = ()) -> list[dict[str, Any]]:
        key = (record_id, def_index)
        if key in trail:
            raise RuntimeError(f"J-Ono refer cycle detected: {trail + (key,)}")
        definition = by_id[record_id]["definition"][def_index - 1]
        resolved: list[dict[str, Any]] = []
        refer = str(definition.get("refer") or "").strip()
        parsed = parse_refer(refer)
        if parsed:
            target_id, target_index = parsed
            resolved.extend(resolve_meanings(target_id, target_index, trail + (key,)))
        local = str(definition.get("meaning") or "").strip()
        if local:
            resolved.append(
                {
                    "source_record_id": record_id,
                    "source_definition_index": def_index,
                    "meaning": local,
                    "via_refer": key != trail[0] if trail else False,
                }
            )
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, int, str]] = set()
        for item in resolved:
            sig = (
                str(item["source_record_id"]),
                int(item["source_definition_index"]),
                str(item["meaning"]),
            )
            if sig in seen:
                continue
            seen.add(sig)
            deduped.append(item)
        return deduped

    output_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_records = 0
    resolved_meaning_empty = 0
    with output_path.open("w", encoding="utf-8", newline="\n") as output:
        for record_id in sorted(by_id):
            item = by_id[record_id]
            romaji = as_strings(item.get("romaji", []), "romaji", record_id)
            katakana = as_strings(item.get("katakana", []), "katakana", record_id)
            hiragana = as_strings(item.get("hiragana", []), "hiragana", record_id)
            for def_index, definition in enumerate(item["definition"], 1):
                resolved = resolve_meanings(record_id, def_index)
                if not resolved:
                    resolved_meaning_empty += 1
                examples = []
                for example in definition.get("example", []):
                    examples.append(
                        {
                            "source": str(example.get("source") or ""),
                            "file": str(example.get("file") or ""),
                            "display": str(example.get("display") or ""),
                            "contributor": str(example.get("contributor") or ""),
                            "image_payload_included": False,
                        }
                    )
                record = {
                    "record_id": f"{record_id}:{def_index:03d}",
                    "definition_id": record_id,
                    "definition_index": def_index,
                    "romaji": romaji,
                    "katakana": katakana,
                    "hiragana": hiragana,
                    "local_meaning": str(definition.get("meaning") or ""),
                    "resolved_meaning_evidence": resolved,
                    "equivalents": as_strings(
                        definition.get("equivalent", []),
                        "equivalent",
                        f"{record_id}:{def_index}",
                    ),
                    "refer": str(definition.get("refer") or ""),
                    "type_code": str(definition.get("type") or ""),
                    "type_label": spec.get("type_map", {}).get(
                        str(definition.get("type") or ""), ""
                    ),
                    "examples": examples,
                    "source": {
                        "dataset": spec["title"],
                        "data_url": spec["data_url"],
                        "source_records_url": spec["source_records_url"],
                        "repository": spec["repository"],
                        "license": spec["license"],
                        "license_url": spec["license_url"],
                        "copyright": spec["copyright"],
                        "data_sha256": sha256_file(data_path),
                    },
                    "meaning_policy": spec["meaning_policy"],
                }
                output.write(
                    json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                    + "\n"
                )
                normalized_records += 1

    source_output_path.parent.mkdir(parents=True, exist_ok=True)
    with source_output_path.open("w", encoding="utf-8", newline="\n") as output:
        for item in sorted(normalized_source_records, key=lambda x: x["source_id"]):
            output.write(
                json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n"
            )

    report = {
        "status": "NORMALIZED",
        "source_definition_records": len(by_id),
        "definition_children": definition_children,
        "normalized_records": normalized_records,
        "surface_variant_count": surface_variant_count,
        "local_meaning_nonempty": local_meaning_nonempty,
        "local_meaning_empty": local_meaning_empty,
        "resolved_meaning_empty": resolved_meaning_empty,
        "refer_edges": len(refer_edges),
        "type_counts": dict(sorted(type_counts.items())),
        "example_metadata_records": example_count,
        "source_metadata_records": len(normalized_source_records),
        "image_payloads_included": False,
        "data_sha256": sha256_file(data_path),
        "source_records_sha256": sha256_file(sources_path),
        "license_sha256": sha256_file(license_path),
        "normalized_sha256": sha256_file(output_path),
        "source_metadata_normalized_sha256": sha256_file(source_output_path),
        "definition_fabricated": False,
        "llm_api_used": False,
        "web_scraping_used": False,
    }
    if normalized_records != definition_children:
        raise RuntimeError("J-Ono definition child record loss")
    if resolved_meaning_empty:
        raise RuntimeError(
            f"J-Ono definitions without source-derived meaning after refer resolution: {resolved_meaning_empty}"
        )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lock_path.write_text(
        json.dumps(
            {
                "data_sha256": report["data_sha256"],
                "source_records_sha256": report["source_records_sha256"],
                "license_sha256": report["license_sha256"],
                "normalized_sha256": report["normalized_sha256"],
                "records": normalized_records,
                "license": spec["license"],
                "copyright": spec["copyright"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--license", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    args = parser.parse_args()
    report = normalize(
        args.manifest,
        args.data,
        args.sources,
        args.license,
        args.output,
        args.source_output,
        args.report,
        args.lock,
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
