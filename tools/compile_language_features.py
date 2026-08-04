#!/usr/bin/env python3
"""Compile approved language-feature YAML fragments into immutable runtime chunks."""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
_LITERAL_INDEX_PATH = ROOT / "src/deterministic_japanese_parser_mcp/literal_index.py"
_spec = importlib.util.spec_from_file_location(
    "djpmcp_literal_index_build", _LITERAL_INDEX_PATH
)
if _spec is None or _spec.loader is None:
    raise RuntimeError("cannot load literal_index.py for build")
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
LiteralIndex = _module.LiteralIndex

ALLOWED_FEATURE_TYPES = {
    "onomatopoeia", "sensory_expression", "metaphor", "metonymy",
    "sociolect", "slang", "modality", "honorific",
    "treatment_expression", "discourse_marker", "backchannel",
    "sentence_final_particle", "information_territory", "interaction_rule",
}
ALLOWED_MATCH_MODES = {"substring", "token", "sentence_final", "exact"}
ALLOWED_FALLBACKS = {"RESOLVED", "AMBIGUOUS", "UNSUPPORTED"}
PART_SIZE = 12000


def _approved_fragments(source_dir: Path) -> dict[str, dict[str, Any]]:
    path = source_dir / "approvals.yaml"
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if value.get("schema_version") != "1.0.0":
        raise ValueError("unsupported language feature approval schema")
    approved = value.get("approved_fragments", {})
    if not isinstance(approved, dict):
        raise ValueError("approved_fragments must be an object")
    return approved


def load_entries(source_dir: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    ids: set[str] = set()
    interpretation_ids: set[str] = set()
    approvals = _approved_fragments(source_dir)
    paths = sorted(
        path for path in source_dir.glob("*.yaml")
        if path.name != "approvals.yaml"
    )
    if not paths:
        raise ValueError(f"no language feature fragments: {source_dir}")
    for path in paths:
        approval = approvals.get(path.name, {})
        if approval.get("status") != "approved":
            raise ValueError(f"unapproved language feature fragment: {path.name}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != approval.get("source_sha256"):
            raise ValueError(
                f"approved fragment digest mismatch: {path.name}: {digest}"
            )
        if not approval.get("review_id"):
            raise ValueError(f"approval review_id is required: {path.name}")
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
                if not interpretation_id or interpretation_id in interpretation_ids:
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
                        raise ValueError(f"evidence.{key} is required: {entry_id}")
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
    return {**core, "content_sha256": hashlib.sha256(encoded).hexdigest()}


def payload_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def build_chunks(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    raw = payload_bytes(payload)
    encoded = base64.b64encode(raw).decode("ascii")
    parts = {
        f"part-{index:04d}.b64": encoded[start : start + PART_SIZE]
        for index, start in enumerate(range(0, len(encoded), PART_SIZE), 1)
    }
    manifest = {
        "schema_version": "1.0.0",
        "encoding": "base64-json-utf8",
        "compiled_sha256": hashlib.sha256(raw).hexdigest(),
        "payload_content_sha256": payload["content_sha256"],
        "entry_count": payload["entry_count"],
        "surface_count": payload["surface_count"],
        "part_size": PART_SIZE,
        "parts": [
            {
                "path": name,
                "sha256": hashlib.sha256(content.encode("ascii")).hexdigest(),
                "characters": len(content),
            }
            for name, content in parts.items()
        ],
    }
    return manifest, parts


def expected_files(payload: dict[str, Any]) -> dict[str, str]:
    manifest, parts = build_chunks(payload)
    return {
        "manifest.json": json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n",
        **{name: content + "\n" for name, content in parts.items()},
    }


def write_output(output_dir: Path, files: dict[str, str]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    expected = set(files)
    for path in output_dir.iterdir():
        if path.is_file() and path.name not in expected:
            path.unlink()
    for name, content in files.items():
        (output_dir / name).write_text(
            content,
            encoding="ascii" if name.endswith(".b64") else "utf-8",
        )


def check_output(output_dir: Path, files: dict[str, str]) -> None:
    actual_names = {
        path.name for path in output_dir.iterdir() if path.is_file()
    } if output_dir.exists() else set()
    if actual_names != set(files):
        raise RuntimeError(
            "compiled language feature asset file set is stale: "
            f"expected={sorted(files)} actual={sorted(actual_names)}"
        )
    for name, expected in files.items():
        actual = (output_dir / name).read_text(
            encoding="ascii" if name.endswith(".b64") else "utf-8"
        )
        if actual != expected:
            raise RuntimeError(f"compiled language feature asset is stale: {name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=ROOT / "dictionaries/system/language_features.d",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "dictionaries/system/compiled/language_features.d",
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = compile_payload(args.source_dir)
    files = expected_files(payload)
    if args.check:
        check_output(args.output_dir, files)
        print({
            "status": "OK",
            "entries": payload["entry_count"],
            "surfaces": payload["surface_count"],
            "sha256": payload["content_sha256"],
            "parts": len(files) - 1,
        })
        return 0
    write_output(args.output_dir, files)
    print({
        "status": "WRITTEN",
        "entries": payload["entry_count"],
        "surfaces": payload["surface_count"],
        "sha256": payload["content_sha256"],
        "parts": len(files) - 1,
        "output": str(args.output_dir),
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
