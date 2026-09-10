#!/usr/bin/env python3
"""Validate whether the compiled dictionary is deployable as completed runtime.

The checked-in 120k Open Lexicon is a lexical identity snapshot. It is useful
for fallback lookup, but it is not the completed semantic dictionary. The
completed deployment path is the direct-final runtime bundle compiled into the
existing OpenLexiconRuntime and SemanticDataRuntime ABIs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


INTEGRATION_SCHEMA = "djpmcp.direct-final-integration.v1"
TARGET = "Deterministic-Japanese-Parser-MCP"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_contract(
    *,
    compiled_root: Path,
    require_direct_final: bool = False,
    expected_source_records: int | None = None,
) -> dict[str, Any]:
    compiled_root = compiled_root.resolve()
    open_manifest_path = compiled_root / "open_lexicon" / "manifest.json"
    semantic_manifest_path = compiled_root / "canonical_dictionary_runtime" / "manifest.json"
    integration_path = compiled_root / "direct_final_integration.json"

    failures: list[str] = []
    warnings: list[str] = []
    if not open_manifest_path.is_file():
        failures.append(f"open lexicon manifest missing: {open_manifest_path}")
        open_manifest: dict[str, Any] = {}
    else:
        open_manifest = _read_json(open_manifest_path)

    integration: dict[str, Any] | None = None
    if integration_path.is_file():
        integration = _read_json(integration_path)

    direct_final = bool(
        integration
        and integration.get("schema_version") == INTEGRATION_SCHEMA
        and integration.get("target") == TARGET
        and integration.get("factory_used") is False
        and open_manifest.get("direct_final_runtime") is True
        and open_manifest.get("factory_used") is False
    )

    if require_direct_final and not direct_final:
        failures.append(
            "completed semantic deployment requires compiled direct-final runtime"
        )

    if open_manifest:
        safety_flags = {
            "exact_lookup_only": True,
            "reading_alias_promotion": False,
            "semantic_auto_promotion": False,
            "intent_auto_promotion": False,
            "external_action_auto_promotion": False,
        }
        for name, expected in safety_flags.items():
            if open_manifest.get(name) is not expected:
                failures.append(
                    f"open lexicon safety flag mismatch: {name}={open_manifest.get(name)!r}"
                )

    semantic_manifest: dict[str, Any] | None = None
    if semantic_manifest_path.is_file():
        semantic_manifest = _read_json(semantic_manifest_path)

    semantic_records = 0
    if direct_final:
        assert integration is not None
        source_records = int(integration.get("source_runtime_records", 0))
        semantic_records = int(integration.get("semantic_records", 0))
        if expected_source_records is not None and source_records != expected_source_records:
            failures.append(
                "direct-final source record count mismatch: "
                f"expected={expected_source_records} actual={source_records}"
            )
        if semantic_records < 1:
            failures.append("direct-final runtime contains no semantic records")
        if semantic_manifest is None:
            failures.append("direct-final semantic runtime manifest missing")
        else:
            if semantic_manifest.get("approved_only") is not True:
                failures.append("semantic runtime is not approved-only")
            if semantic_manifest.get("automatic_external_action") is not False:
                failures.append("semantic runtime external-action boundary is invalid")
            if semantic_manifest.get("direct_final_runtime") is not True:
                failures.append("semantic runtime is not marked as direct-final")
            if semantic_manifest.get("factory_used") is not False:
                failures.append("semantic runtime must preserve factory_used=false")
    else:
        if open_manifest.get("record_count") == 120000:
            warnings.append(
                "checked-in 120k Open Lexicon is lexical identity only; "
                "do not deploy it as completed semantic runtime"
            )

    status = "PASS" if not failures else "FAIL"
    return {
        "status": status,
        "compiled_root": str(compiled_root),
        "completed_semantic_deployable": direct_final and not failures,
        "direct_final_runtime": direct_final,
        "require_direct_final": require_direct_final,
        "open_lexicon_records": int(open_manifest.get("record_count", 0) or 0),
        "semantic_records": semantic_records,
        "integration_manifest": str(integration_path) if integration else None,
        "failures": failures,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--compiled-root",
        type=Path,
        default=Path("dictionaries/system/compiled"),
    )
    parser.add_argument("--require-direct-final", action="store_true")
    parser.add_argument("--expected-source-records", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = evaluate_contract(
        compiled_root=args.compiled_root,
        require_direct_final=args.require_direct_final,
        expected_source_records=args.expected_source_records,
    )
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
