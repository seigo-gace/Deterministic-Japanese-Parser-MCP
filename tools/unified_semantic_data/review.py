"""Deterministic review-batch and human/GPT-app decision-ledger handling."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .common import APPROVAL_SCOPES, _json_line, normalize_text

DECISION_STATUSES = {"approved", "rejected", "hold", "needs-evidence"}
PATCH_FIELDS = {
    "meaning_candidates",
    "parameters",
    "register",
    "context_conditions",
    "examples",
    "domains",
    "usage_labels",
    "semantic_targets",
    "risk_class",
}


def _decision_paths(root: Path | None) -> list[Path]:
    if root is None or not root.exists():
        return []
    return sorted(
        [*root.rglob("*.jsonl"), *root.rglob("*.json")], key=str
    )


def load_decisions(root: Path | None) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    for path in _decision_paths(root):
        if path.suffix == ".jsonl":
            values = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        else:
            value = json.loads(path.read_text(encoding="utf-8"))
            values = value.get("decisions", []) if isinstance(value, dict) else value
        for line_number, item in enumerate(values, 1):
            if not isinstance(item, dict):
                raise ValueError(f"decision must be an object: {path}:{line_number}")
            decision = dict(item)
            required = (
                "decision_id", "record_id", "scope", "status", "reviewer",
                "decided_at", "rationale", "input_sha256",
            )
            missing = [name for name in required if not normalize_text(decision.get(name))]
            if missing:
                raise ValueError(
                    f"decision fields missing {missing}: {path}:{line_number}"
                )
            if decision["scope"] not in APPROVAL_SCOPES:
                raise ValueError(f"invalid decision scope: {decision['scope']}")
            if decision["status"] not in DECISION_STATUSES:
                raise ValueError(f"invalid decision status: {decision['status']}")
            patch = decision.get("patch") or {}
            if not isinstance(patch, dict) or set(patch) - PATCH_FIELDS:
                raise ValueError(
                    f"decision patch contains forbidden fields: {path}:{line_number}"
                )
            decision["_path"] = str(path.relative_to(root))
            decision["_line"] = line_number
            decisions.append(decision)
    ids = [item["decision_id"] for item in decisions]
    duplicate_ids = sorted(key for key, count in Counter(ids).items() if count > 1)
    if duplicate_ids:
        raise ValueError(f"duplicate decision ids: {duplicate_ids[:20]}")
    return sorted(decisions, key=lambda item: item["decision_id"])


def apply_decisions(
    records: list[dict[str, Any]], decisions: Iterable[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_id = {item["record_id"]: item for item in records}
    audit: list[dict[str, Any]] = []
    for decision in decisions:
        record = by_id.get(decision["record_id"])
        if record is None:
            raise ValueError(
                f"decision references unknown record: {decision['record_id']}"
            )
        if decision["input_sha256"] != record.get("input_sha256"):
            raise ValueError(
                f"stale decision input digest: {decision['decision_id']}"
            )
        for field, value in (decision.get("patch") or {}).items():
            record[field] = value
        scope = decision["scope"]
        blockers = record["approval"]["blockers_by_scope"].get(scope, [])
        if scope == "semantic" and record.get("meaning_candidates"):
            blockers = [item for item in blockers if item != "meaning-candidate-required"]
        if scope == "pragmatic":
            examples = record.get("examples") or {}
            for name in ("positive", "negative", "boundary"):
                if examples.get(name):
                    blockers = [
                        item for item in blockers if item != f"{name}-example-required"
                    ]
        record["approval"]["blockers_by_scope"][scope] = blockers
        record["approval"]["scopes"][scope] = decision["status"]
        if decision["status"] == "approved" and blockers:
            raise ValueError(
                f"decision cannot approve blocked scope: {decision['decision_id']} {blockers}"
            )
        approved = sorted(
            name
            for name, status in record["approval"]["scopes"].items()
            if status == "approved"
            and not record["approval"]["blockers_by_scope"].get(name)
        )
        review = sorted(
            name
            for name, status in record["approval"]["scopes"].items()
            if status not in {"approved", "not-applicable", "rejected"}
            or bool(record["approval"]["blockers_by_scope"].get(name))
        )
        record["approval"]["approved_scopes"] = approved
        record["approval"]["review_scopes"] = review
        record["runtime_eligible"] = "lexical" in approved
        record.setdefault("decision_ids", []).append(decision["decision_id"])
        audit.append({
            "decision_id": decision["decision_id"],
            "record_id": record["record_id"],
            "scope": scope,
            "status": decision["status"],
            "reviewer": decision["reviewer"],
            "decided_at": decision["decided_at"],
            "source": f"{decision['_path']}:{decision['_line']}",
        })
    return records, audit


def write_review_batches(
    records: list[dict[str, Any]], output_root: Path, *, batch_size: int = 20
) -> list[dict[str, Any]]:
    if batch_size < 1 or batch_size > 20:
        raise ValueError("review batch size must be between 1 and 20")
    batch_root = output_root / "review-batches"
    batch_root.mkdir(parents=True, exist_ok=True)
    manifests: list[dict[str, Any]] = []
    for start in range(0, len(records), batch_size):
        selected = records[start : start + batch_size]
        number = start // batch_size + 1
        payload = {
            "schema_version": "1.0.0",
            "batch_id": f"unified-semantic-{number:04d}",
            "runtime_promotion_allowed": False,
            "instructions": (
                "GPTアプリで各scopeを検討し、別ファイルのDecision Ledgerを作成する。"
                "このbatch自体は編集せず、自動承認しない。"
            ),
            "records": selected,
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        name = f"batch-{number:04d}.json"
        (batch_root / name).write_text(text, encoding="utf-8", newline="\n")
        manifests.append({
            "batch_id": payload["batch_id"],
            "path": f"review-batches/{name}",
            "record_count": len(selected),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        })
    index_text = "".join(_json_line(item) + "\n" for item in manifests)
    (output_root / "review-batch-index.jsonl").write_text(
        index_text, encoding="utf-8", newline="\n"
    )
    return manifests
