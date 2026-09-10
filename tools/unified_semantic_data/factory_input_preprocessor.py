"""Complete heterogeneous source rows before they enter the dictionary factory.

The preprocessor validates already-resolved adapter rows, converts every unresolved
source row into one deterministic completion item, and applies only explicit,
evidence-bearing build-time supplements.  It never approves meaning candidates or
promotes records into runtime assets.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Iterator

from .source_adapter_contract import normalize_adapter_record


PREPROCESSOR_VERSION = "1.0.0"
COMPLETION_METHOD = "chatgpt-build-time"
_LIST_FIELDS = {"surfaces", "meanings"}
_SOURCE_FIELDS = {"dataset", "version", "license", "source_id", "source_sha256"}


def _json_line(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_jsonl(path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    opener = gzip.open if path.name.endswith(".gz") else Path.open
    with opener(path, "rt", encoding="utf-8") as handle:  # type: ignore[arg-type]
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"JSONL row must be object: {path}:{line_number}")
            yield line_number, value


def _completion_id(kind: str, role: str, row: dict[str, Any]) -> str:
    identity = {
        "kind": kind,
        "role": role,
        "source_record_sha256": row.get("source_record_sha256"),
        "source_id": row.get("source_id"),
        "payload_path": row.get("payload_path"),
        "record_number": row.get("record_number", row.get("line")),
    }
    return "PREFAC-" + hashlib.sha256(_json_line(identity).encode("utf-8")).hexdigest()[:32]


def _role_base(row: dict[str, Any], role: str, completion_id: str) -> dict[str, Any]:
    source = row.get("source")
    if not isinstance(source, dict):
        raise ValueError(f"unresolved role source missing: {completion_id}")
    value = row.get("value")
    if not isinstance(value, dict):
        raise ValueError(f"unresolved role value missing: {completion_id}")
    return {
        "adapter_record_id": f"{completion_id}-{hashlib.sha256(role.encode()).hexdigest()[:8]}",
        "source_role": role,
        "surfaces": [],
        "readings": [],
        "part_of_speech_list": [],
        "domains": [],
        "payload": {
            "preprocessor_version": PREPROCESSOR_VERSION,
            "source_value": value,
        },
        "source": source,
    }


def _queue_items(path: Path) -> Iterator[dict[str, Any]]:
    for line_number, row in _iter_jsonl(path):
        roles = sorted(
            {
                str(value).strip()
                for value in row.get("source_roles", [])
                if str(value).strip()
            }
        )
        if not roles:
            raise ValueError(f"unresolved source_roles missing: {path}:{line_number}")
        kind = "meaning" if "base_adapter_record" in row else "auxiliary-role"
        for role in roles:
            completion_id = _completion_id(kind, role, row)
            if kind == "meaning":
                base = deepcopy(row["base_adapter_record"])
                if role != base.get("source_role"):
                    raise ValueError(f"meaning completion role mismatch: {completion_id}")
                missing = sorted(set(row.get("missing_required_fields") or []))
            else:
                base = _role_base(row, role, completion_id)
                missing = ["surfaces"]
            if not missing:
                raise ValueError(f"unresolved row has no missing required fields: {completion_id}")
            yield {
                "schema_version": PREPROCESSOR_VERSION,
                "completion_id": completion_id,
                "source_kind": kind,
                "source_role": role,
                "reason": str(row.get("reason") or "REQUIRED_FIELD_MISSING"),
                "missing_required_fields": missing,
                "source_record_sha256": str(row.get("source_record_sha256") or ""),
                "base_adapter_record": base,
                "original_record": row.get("value"),
                "automatic_approval": False,
                "automatic_runtime_promotion": False,
            }


def _load_supplements(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    decisions: dict[str, dict[str, Any]] = {}
    for line_number, row in _iter_jsonl(path):
        completion_id = str(row.get("completion_id") or "").strip()
        if not completion_id:
            raise ValueError(f"supplement completion_id required: {path}:{line_number}")
        if completion_id in decisions:
            raise ValueError(f"duplicate supplement completion_id: {completion_id}")
        decisions[completion_id] = row
    return decisions


def _nonempty_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({str(item).strip() for item in value if str(item).strip()})


def _apply_supplement(item: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    if decision.get("method") != COMPLETION_METHOD:
        raise ValueError(f"supplement method must be {COMPLETION_METHOD}: {item['completion_id']}")
    evidence = _nonempty_strings(decision.get("evidence"))
    rationale = str(decision.get("rationale") or "").strip()
    patch = decision.get("patch")
    if not evidence or not rationale or not isinstance(patch, dict) or not patch:
        raise ValueError(
            "supplement evidence, rationale, and patch required: "
            f"{item['completion_id']}"
        )

    missing = set(item["missing_required_fields"])
    supplied: set[str] = set()
    unexpected = set(patch) - (_LIST_FIELDS | {"source"})
    if unexpected:
        raise ValueError(
            "supplement cannot overwrite non-missing fields: "
            f"{item['completion_id']}:{sorted(unexpected)}"
        )
    completed = deepcopy(item["base_adapter_record"])
    for field in _LIST_FIELDS:
        if field not in patch:
            continue
        if field not in missing:
            raise ValueError(f"supplement field was not missing: {item['completion_id']}:{field}")
        values = _nonempty_strings(patch[field])
        if not values:
            raise ValueError(f"supplement list field is empty: {item['completion_id']}:{field}")
        completed[field] = values
        supplied.add(field)
    source_patch = patch.get("source", {})
    if not isinstance(source_patch, dict):
        raise ValueError(f"supplement source patch must be object: {item['completion_id']}")
    for field, value in source_patch.items():
        path = f"source.{field}"
        if field not in _SOURCE_FIELDS or path not in missing:
            raise ValueError(
                "supplement source field was not missing: "
                f"{item['completion_id']}:{path}"
            )
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"supplement source field is empty: {item['completion_id']}:{path}")
        completed.setdefault("source", {})[field] = text
        supplied.add(path)
    if supplied != missing:
        raise ValueError(
            f"supplement must fill every missing field: {item['completion_id']}:"
            f"missing={sorted(missing - supplied)}"
        )

    payload = completed.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    payload["factory_input_completion"] = {
        "completion_id": item["completion_id"],
        "method": COMPLETION_METHOD,
        "supplemented_fields": sorted(supplied),
        "evidence": evidence,
        "rationale": rationale,
        "source_record_sha256": item["source_record_sha256"],
        "automatic_approval": False,
        "automatic_runtime_promotion": False,
    }
    completed["payload"] = payload
    return normalize_adapter_record(completed, path=Path("<supplement>"), line=1)


def build_factory_input_preprocessor(
    adapter_inputs: Iterable[Path],
    unresolved_inputs: Iterable[Path],
    output_root: Path,
    *,
    supplements_path: Path | None = None,
    require_complete: bool = False,
) -> dict[str, Any]:
    """Validate common-shape inputs and produce the gated completion lane."""
    adapters = sorted(set(adapter_inputs), key=str)
    unresolved = sorted(set(unresolved_inputs), key=str)
    if not adapters or not unresolved:
        raise ValueError("adapter_inputs and unresolved_inputs are required")
    for path in [*adapters, *unresolved]:
        if not path.is_file():
            raise ValueError(f"preprocessor input missing: {path}")
    if supplements_path is not None and not supplements_path.is_file():
        raise ValueError(f"supplement file missing: {supplements_path}")

    output_root.mkdir(parents=True, exist_ok=True)
    queue_path = output_root / "factory-input-completion-queue.jsonl"
    completed_path = output_root / "supplemented-adapter-records.jsonl"
    index_path = output_root / "adapter-record-index.sqlite3"
    counts: Counter[str] = Counter()
    input_files: list[dict[str, Any]] = []

    with sqlite3.connect(index_path) as database:
        database.execute("CREATE TABLE records (id TEXT PRIMARY KEY, input_path TEXT NOT NULL)")
        for path in adapters:
            file_count = 0
            for line_number, raw in _iter_jsonl(path):
                record = normalize_adapter_record(raw, path=path, line=line_number)
                try:
                    database.execute(
                        "INSERT INTO records(id, input_path) VALUES (?, ?)",
                        (record["adapter_record_id"], str(path)),
                    )
                except sqlite3.IntegrityError as exc:
                    raise ValueError(
                        f"duplicate adapter record id: {record['adapter_record_id']}"
                    ) from exc
                file_count += 1
                counts["validated_adapter_records"] += 1
            input_files.append({
                "path": path.name,
                "sha256": _sha256_file(path),
                "record_count": file_count,
            })

        items: dict[str, dict[str, Any]] = {}
        for path in unresolved:
            for item in _queue_items(path):
                completion_id = item["completion_id"]
                if completion_id in items:
                    raise ValueError(f"duplicate completion id: {completion_id}")
                items[completion_id] = item
                counts["completion_items"] += 1
                counts["unresolved_required_fields_before"] += len(item["missing_required_fields"])

        decisions = _load_supplements(supplements_path)
        unknown = sorted(set(decisions) - set(items))
        if unknown:
            raise ValueError(f"supplements reference unknown completion ids: {unknown[:5]}")

        with (
            queue_path.open("w", encoding="utf-8", newline="\n") as queue,
            completed_path.open("w", encoding="utf-8", newline="\n") as completed_output,
        ):
            for completion_id in sorted(items):
                item = items[completion_id]
                decision = decisions.get(completion_id)
                if decision is None:
                    queue.write(_json_line(item) + "\n")
                    counts["remaining_completion_items"] += 1
                    counts["unresolved_required_fields"] += len(item["missing_required_fields"])
                    continue
                record = _apply_supplement(item, decision)
                try:
                    database.execute(
                        "INSERT INTO records(id, input_path) VALUES (?, ?)",
                        (record["adapter_record_id"], str(completed_path)),
                    )
                except sqlite3.IntegrityError as exc:
                    raise ValueError(
                        "completed adapter record id collision: "
                        f"{record['adapter_record_id']}"
                    ) from exc
                completed_output.write(_json_line(record) + "\n")
                counts["supplemented_adapter_records"] += 1
        database.commit()

    index_path.unlink()
    factory_input_count = (
        counts["validated_adapter_records"] + counts["supplemented_adapter_records"]
    )
    report = {
        "schema_version": PREPROCESSOR_VERSION,
        "mode": "deterministic-prefactory-input-completion",
        "status": (
            "READY_FOR_FACTORY"
            if counts["unresolved_required_fields"] == 0
            else "COMPLETION_REQUIRED"
        ),
        "factory_input_complete": counts["unresolved_required_fields"] == 0,
        "validated_adapter_record_count": counts["validated_adapter_records"],
        "completion_item_count": counts["completion_items"],
        "supplemented_adapter_record_count": counts["supplemented_adapter_records"],
        "remaining_completion_item_count": counts["remaining_completion_items"],
        "unresolved_required_fields_before": counts["unresolved_required_fields_before"],
        "unresolved_required_fields": counts["unresolved_required_fields"],
        "factory_input_record_count": factory_input_count,
        "input_files": input_files,
        "outputs": {
            queue_path.name: {
                "sha256": _sha256_file(queue_path),
                "bytes": queue_path.stat().st_size,
            },
            completed_path.name: {
                "sha256": _sha256_file(completed_path),
                "bytes": completed_path.stat().st_size,
            },
        },
        "boundaries": {
            "common_adapter_shape_validated": True,
            "original_record_preserved_in_completion_queue": True,
            "evidence_required_for_supplement": True,
            "only_missing_required_fields_may_be_supplemented": True,
            "incomplete_records_blocked_from_factory": True,
            "automatic_approval": False,
            "automatic_runtime_promotion": False,
        },
    }
    report_path = output_root / "factory-input-preprocessor-report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if require_complete and not report["factory_input_complete"]:
        raise RuntimeError(
            "PREFACTORY_INPUT_INCOMPLETE:"
            f"unresolved_required_fields={report['unresolved_required_fields']}"
        )
    return report
