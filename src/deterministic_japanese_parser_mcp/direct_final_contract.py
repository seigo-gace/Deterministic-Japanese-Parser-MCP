"""Shared validation for the compiled Direct Final runtime contract."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


INTEGRATION_SCHEMA = "djpmcp.direct-final-integration.v1"
TARGET = "Deterministic-Japanese-Parser-MCP"
_SHA256_LENGTH = 64


class DirectFinalContractError(RuntimeError):
    """Raised when a process requires an invalid Direct Final runtime."""


def _read_json(
    path: Path,
    *,
    component: str,
    failures: list[str],
) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"{component} manifest invalid: {path}: {exc}")
        return {}
    if not isinstance(value, dict):
        failures.append(f"{component} manifest must be a JSON object: {path}")
        return {}
    return value


def _int_field(
    payload: dict[str, Any],
    name: str,
    *,
    component: str,
    failures: list[str],
) -> int:
    try:
        return int(payload.get(name, 0))
    except (TypeError, ValueError):
        failures.append(
            f"{component} {name} must be an integer: {payload.get(name)!r}"
        )
        return 0


def _valid_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == _SHA256_LENGTH and all(
        character in "0123456789abcdef" for character in text
    )


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_output_files(
    *,
    root: Path,
    outputs: Any,
    failures: list[str],
) -> tuple[int, int]:
    if not isinstance(outputs, list) or not outputs:
        failures.append("direct-final semantic runtime outputs are missing")
        return 0, 0

    record_count = 0
    record_shards = 0
    root_resolved = root.resolve()
    for number, output in enumerate(outputs):
        if not isinstance(output, dict):
            failures.append(
                f"direct-final semantic output #{number} must be an object"
            )
            continue
        relative = str(output.get("path") or "")
        path = root / relative
        try:
            path.resolve().relative_to(root_resolved)
        except ValueError:
            failures.append(
                f"direct-final semantic output escapes runtime root: {relative}"
            )
            continue
        if not path.is_file():
            failures.append(f"direct-final semantic output missing: {path}")
            continue
        expected_bytes = _int_field(
            output,
            "bytes",
            component=f"direct-final semantic output {relative}",
            failures=failures,
        )
        if expected_bytes < 1 or path.stat().st_size != expected_bytes:
            failures.append(
                "direct-final semantic output size mismatch: "
                f"{relative} expected={expected_bytes} actual={path.stat().st_size}"
            )
        declared_sha = output.get("sha256")
        if not _valid_sha256(declared_sha):
            failures.append(
                f"direct-final semantic output sha256 invalid: {relative}"
            )
        elif _sha256(path) != declared_sha:
            failures.append(
                f"direct-final semantic output sha256 mismatch: {relative}"
            )
        if relative.startswith("records/"):
            record_shards += 1
            record_count += _int_field(
                output,
                "record_count",
                component=f"direct-final semantic output {relative}",
                failures=failures,
            )
    return record_count, record_shards


def evaluate_contract(
    *,
    compiled_root: Path,
    require_direct_final: bool = False,
    expected_source_records: int | None = None,
) -> dict[str, Any]:
    """Evaluate the existing compiled-runtime and integration manifests."""
    compiled_root = compiled_root.resolve()
    open_root = compiled_root / "open_lexicon"
    semantic_root = compiled_root / "canonical_dictionary_runtime"
    open_manifest_path = open_root / "manifest.json"
    semantic_manifest_path = semantic_root / "manifest.json"
    integration_path = compiled_root / "direct_final_integration.json"

    failures: list[str] = []
    warnings: list[str] = []
    if not open_manifest_path.is_file():
        failures.append(f"open lexicon manifest missing: {open_manifest_path}")
        open_manifest: dict[str, Any] = {}
    else:
        open_manifest = _read_json(
            open_manifest_path,
            component="open lexicon",
            failures=failures,
        )

    integration: dict[str, Any] | None = None
    if integration_path.is_file():
        integration = _read_json(
            integration_path,
            component="direct-final integration",
            failures=failures,
        )
    elif require_direct_final:
        failures.append(
            f"direct-final integration manifest missing: {integration_path}"
        )

    direct_final = bool(
        integration
        and integration.get("schema_version") == INTEGRATION_SCHEMA
        and integration.get("target") == TARGET
        and integration.get("factory_used") is False
        and open_manifest.get("direct_final_runtime") is True
        and open_manifest.get("factory_used") is False
    )

    if require_direct_final and integration:
        if integration.get("schema_version") != INTEGRATION_SCHEMA:
            failures.append("direct-final integration schema mismatch")
        if integration.get("target") != TARGET:
            failures.append("direct-final integration target mismatch")
        if integration.get("factory_used") is not False:
            failures.append(
                "direct-final integration must preserve factory_used=false"
            )
    if require_direct_final and open_manifest:
        if open_manifest.get("direct_final_runtime") is not True:
            failures.append("open lexicon manifest is not marked as direct-final")
        if open_manifest.get("factory_used") is not False:
            failures.append("open lexicon manifest must preserve factory_used=false")

    if require_direct_final and not direct_final:
        failures.insert(
            0,
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
                    f"open lexicon safety flag mismatch: "
                    f"{name}={open_manifest.get(name)!r}"
                )

    semantic_manifest: dict[str, Any] | None = None
    if semantic_manifest_path.is_file():
        semantic_manifest = _read_json(
            semantic_manifest_path,
            component="direct-final semantic runtime",
            failures=failures,
        )
    elif require_direct_final:
        failures.append(
            f"direct-final semantic runtime manifest missing: {semantic_manifest_path}"
        )

    semantic_records = 0
    if direct_final:
        assert integration is not None
        if integration.get("schema_version") != INTEGRATION_SCHEMA:
            failures.append("direct-final integration schema mismatch")
        if integration.get("target") != TARGET:
            failures.append("direct-final integration target mismatch")
        if integration.get("factory_used") is not False:
            failures.append("direct-final integration must preserve factory_used=false")

        source_records = _int_field(
            integration,
            "source_runtime_records",
            component="direct-final integration",
            failures=failures,
        )
        semantic_records = _int_field(
            integration,
            "semantic_records",
            component="direct-final integration",
            failures=failures,
        )
        open_records = _int_field(
            open_manifest,
            "record_count",
            component="open lexicon manifest",
            failures=failures,
        )
        expected_open_records = _int_field(
            open_manifest,
            "expected_record_count",
            component="open lexicon manifest",
            failures=failures,
        )
        if source_records < 1:
            failures.append("direct-final runtime contains no open lexicon records")
        if source_records != open_records or open_records != expected_open_records:
            failures.append(
                "direct-final open lexicon record count mismatch: "
                f"integration={source_records} manifest={open_records} "
                f"expected={expected_open_records}"
            )
        if expected_source_records is not None and source_records != expected_source_records:
            failures.append(
                "direct-final source record count mismatch: "
                f"expected={expected_source_records} actual={source_records}"
            )

        source_sha = integration.get("source_manifest_sha256")
        if not _valid_sha256(source_sha):
            failures.append("direct-final source manifest sha256 is invalid")
        if open_manifest.get("source_manifest_sha256") != source_sha:
            failures.append("direct-final open lexicon source manifest mismatch")
        if integration.get("open_lexicon") != open_manifest:
            failures.append(
                "direct-final integration open lexicon manifest is inconsistent"
            )

        sqlite_meta = open_manifest.get("sqlite") or {}
        sqlite_relative = str(sqlite_meta.get("path") or "")
        sqlite_path = open_root / sqlite_relative
        if sqlite_relative != "lexicon.sqlite3":
            failures.append(
                "direct-final open lexicon database path mismatch: "
                f"{sqlite_relative!r}"
            )
        if not sqlite_path.is_file():
            failures.append(f"direct-final open lexicon database missing: {sqlite_path}")
        else:
            sqlite_bytes = _int_field(
                sqlite_meta,
                "bytes",
                component="direct-final open lexicon database",
                failures=failures,
            )
            if sqlite_bytes < 1 or sqlite_path.stat().st_size != sqlite_bytes:
                failures.append(
                    "direct-final open lexicon database size mismatch: "
                    f"expected={sqlite_bytes} actual={sqlite_path.stat().st_size}"
                )
        declared_sqlite_sha = sqlite_meta.get("sha256")
        if not _valid_sha256(declared_sqlite_sha):
            failures.append("direct-final open lexicon database sha256 is invalid")
        elif sqlite_path.is_file() and _sha256(sqlite_path) != declared_sqlite_sha:
            failures.append("direct-final open lexicon database sha256 mismatch")

        if semantic_records < 1:
            failures.append("direct-final runtime contains no semantic records")
        if semantic_manifest is not None:
            semantic_manifest_records = _int_field(
                semantic_manifest,
                "record_count",
                component="direct-final semantic runtime manifest",
                failures=failures,
            )
            if semantic_manifest_records != semantic_records:
                failures.append(
                    "direct-final semantic record count mismatch: "
                    f"integration={semantic_records} "
                    f"manifest={semantic_manifest_records}"
                )
            if semantic_manifest.get("approved_only") is not True:
                failures.append("semantic runtime is not approved-only")
            if semantic_manifest.get("automatic_external_action") is not False:
                failures.append("semantic runtime external-action boundary is invalid")
            if semantic_manifest.get("preserve_ambiguity") is not True:
                failures.append("semantic runtime must preserve ambiguity")
            if semantic_manifest.get("direct_final_runtime") is not True:
                failures.append("semantic runtime is not marked as direct-final")
            if semantic_manifest.get("factory_used") is not False:
                failures.append("semantic runtime must preserve factory_used=false")
            if semantic_manifest.get("source_manifest_sha256") != source_sha:
                failures.append("direct-final semantic source manifest mismatch")
            if integration.get("semantic_runtime") != semantic_manifest:
                failures.append(
                    "direct-final integration semantic manifest is inconsistent"
                )
            output_records, output_shards = _validate_output_files(
                root=semantic_root,
                outputs=semantic_manifest.get("outputs"),
                failures=failures,
            )
            expected_shards = _int_field(
                semantic_manifest,
                "record_shards",
                component="direct-final semantic runtime manifest",
                failures=failures,
            )
            if output_records != semantic_records:
                failures.append(
                    "direct-final semantic output record count mismatch: "
                    f"integration={semantic_records} outputs={output_records}"
                )
            if output_shards != expected_shards:
                failures.append(
                    "direct-final semantic shard count mismatch: "
                    f"manifest={expected_shards} outputs={output_shards}"
                )
    elif open_manifest.get("record_count") == 120000:
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
        "open_lexicon_records": _safe_int(open_manifest.get("record_count")),
        "semantic_records": semantic_records,
        "integration_manifest": str(integration_path) if integration else None,
        "failures": failures,
        "warnings": warnings,
    }


def require_direct_final_runtime(system_root: Path) -> dict[str, Any]:
    """Fail closed unless ``system_root`` is a complete Direct Final runtime."""
    report = evaluate_contract(
        compiled_root=Path(system_root) / "compiled",
        require_direct_final=True,
    )
    if report["status"] != "PASS":
        raise DirectFinalContractError(
            "Direct Final required contract failed: "
            + "; ".join(report["failures"])
        )
    return report
