#!/usr/bin/env python3
"""Compile approved language-feature YAML fragments into a runtime asset."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from deterministic_japanese_parser_mcp.literal_index import LiteralIndex

ALLOWED_FEATURE_TYPES = {
    "onomatopoeia", "sensory_expression", "metaphor", "metonymy",
    "sociolect", "slang", "modality", "honorific",
    "treatment_expression", "discourse_marker", "backchannel",
    "sentence_final_particle", "information_territory", "interaction_rule",
}
ALLOWED_MATCH_MODES = {"substring", "token", "sentence_final", "exact"}
ALLOWED_FALLBACKS = {"RESOLVED", "AMBIGUOUS", "UNSUPPORTED"}


def load_entries(source_dir: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    ids: set[str] = set()
    interpretation_ids: set[str] = set()
    for path in sorted(source_dir.glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if document.get("schema_version") != "1.0.0":
            raise ValueError(f"unsupported source schema: {path}")
        for raw in document.get("entries", []):
            entry = dict(raw)
            entry_id = entry.get("entry_id")
            if not entry_id or entry_id in ids:
                raise ValueError(f"missing or duplicate entry_id: {entry_id}")
            ids.add(entry_id)
            feature_type = entry.get("feature_type")
            if feature_type not in ALLOWED_FEATURE_TYPES:
                raise ValueError(
                    f"unsupported feature_type: {entry_id}: {feature_type}"
                )
            surfaces = entry.get("surfaces", [])
            if not surfaces:
                raise ValueError(f"surfaces are required: {entry_id}")
            normalized_surfaces: list[dict[str, str]] = []
            for surface in surfaces:
                if isinstance(surface, str):
                    value = surface
                    mode = "substring"
                else:
                    value = str(surface.get("value", ""))
                    mode = surface.get("match_mode", "substring")
                if not value or mode not in ALLOWED_MATCH_MODES:
                    raise ValueError(f"invalid surface: {entry_id}: {surface}")
                normalized_surfaces.append({
                    "value": value,
                    "match_mode": mode,
                })
            entry["surfaces"] = normalized_surfaces
            interpretations = entry.get("interpretations", [])
            if not interpretations:
                raise ValueError(f"interpretations are required: {entry_id}")
            for interpretation in interpretations:
                interpretation_id = interpretation.get("interpretation_id")
                if (
                    not interpretation_id
                    or interpretation_id in interpretation_ids
                ):
                    raise ValueError(
                        "missing or duplicate interpretation_id: "
                        f"{interpretation_id}"
                    )
                interpretation_ids.add(interpretation_id)
                if not interpretation.get("label"):
                    raise ValueError(
                        f"interpretation label is required: {interpretation_id}"
                    )
                if not isinstance(interpretation.get("parameters", {}), dict):
                    raise ValueError(
                        f"parameters must be an object: {interpretation_id}"
                    )
            fallback = entry.get("fallback_status", "AMBIGUOUS")
            if fallback not in ALLOWED_FALLBACKS:
                raise ValueError(
                    f"invalid fallback_status: {entry_id}: {fallback}"
                )
            evidence = entry.get("evidence", [])
            if not evidence:
                raise ValueError(f"evidence is required: {entry_id}")
            for item in evidence:
                for key in (
                    "evidence_id", "dataset", "version", "license", "source_id"
                ):
                    if not item.get(key):
                        raise ValueError(
                            f"evidence.{key} is required: {entry_id}"
                        )
            entry["source_fragment"] = path.name
            entries.append(entry)
    return sorted(entries, key=lambda item: item["entry_id"])


def compile_payload(source_dir: Path) -> dict[str, Any]:
    entries = load_entries(source_dir)
    surface_map: dict[str, list[dict[str, str]]] = {}
    for entry in entries:
        for surface in entry["surfaces"]:
            surface_map.setdefault(surface["value"], []).append({
                "entry_id": entry["entry_id"],
                "match_mode": surface["match_mode"],
            })
    surface_map = {
        surface: sorted(
            values,
            key=lambda item: (item["entry_id"], item["match_mode"]),
        )
        for surface, values in sorted(surface_map.items())
    }
    index = LiteralIndex(surface_map)
    core = {
        "schema_version": "1.0.0",
        "entry_count": len(entries),
        "surface_count": len(surface_map),
        "entries": entries,
        "surface_map": surface_map,
        "literal_index": index.to_compiled(),
    }
    encoded = json.dumps(
        core,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        **core,
        "content_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def encoded_payload(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=ROOT / "dictionaries/system/language_features.d",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dictionaries/system/compiled/language_features.json",
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = compile_payload(args.source_dir)
    encoded = encoded_payload(payload)
    if args.check:
        if not args.output.exists():
            raise FileNotFoundError(args.output)
        current = args.output.read_text(encoding="utf-8")
        if current != encoded:
            raise RuntimeError(
                "compiled language feature asset is stale; run "
                "python tools/compile_language_features.py"
            )
        print({
            "status": "OK",
            "entries": payload["entry_count"],
            "surfaces": payload["surface_count"],
            "sha256": payload["content_sha256"],
        })
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded, encoding="utf-8")
    print({
        "status": "WRITTEN",
        "entries": payload["entry_count"],
        "surfaces": payload["surface_count"],
        "sha256": payload["content_sha256"],
        "output": str(args.output),
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
