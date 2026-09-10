#!/usr/bin/env python3
"""Phase 1-4 review station.

Current route: ChatGPT app -> reviewed sample -> deterministic rules. No network.
Future route: external provider interface. OpenAIAPIProvider is a disabled stub.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Callable, Iterable, Iterator, Protocol, TypeVar

import yaml

MAX_BATCH_REQUESTS = 50_000
BATCH_ENDPOINT = "/v1/responses"
REVIEW_SCOPES = ("semantic", "pragmatic", "task", "external_action")
DECISION_STATUSES = {"approved", "needs-evidence", "rejected", "hold"}
PATCH_FIELDS = {
    "meaning_candidates", "parameters", "register", "context_conditions",
    "examples", "domains", "usage_labels", "semantic_targets", "risk_class",
    "polarity", "intensity", "task_candidates", "external_action_risk",
}
DEFAULT_MODEL = "future-external-provider"
DEFAULT_DECIDED_AT = "2026-08-09T02:24:49Z"
T = TypeVar("T")


class ReviewProvider(Protocol):
    provider_name: str

    def review_batch(self, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ...


def _json_line(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_sha256(value: Any) -> bool:
    text = str(value or "").lower()
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def _review_seed_input_sha256(record: dict[str, Any]) -> str:
    """Mirror PR #27 review-seed hashing for the fixed PR #26 queue artifact."""
    if _is_sha256(record.get("input_sha256")):
        return str(record["input_sha256"]).lower()
    raw = dict(record)
    raw["approval_scopes"] = {
        **dict(raw.get("approval_scopes") or {}),
        "lexical": "approved",
        "semantic": "needs-evidence",
        "pragmatic": "needs-evidence",
        "task": "needs-evidence",
        "external_action": "needs-evidence",
    }
    raw["_force_judgment_review"] = True
    value = {key: item for key, item in raw.items() if not key.startswith("_source_")}
    return _sha256_bytes(_json_line(value).encode("utf-8"))


def ensure_input_sha256(record: dict[str, Any]) -> dict[str, Any]:
    value = dict(record)
    value["input_sha256"] = _review_seed_input_sha256(record)
    return value


def iter_queue(path: Path) -> Iterator[dict[str, Any]]:
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"queue row must be an object: {path}:{line_number}")
            row = ensure_input_sha256(row)
            record_id = str(row.get("record_id") or "").strip()
            if not record_id:
                raise ValueError(f"record_id is required at queue index {line_number}")
            if record_id in seen:
                raise ValueError(f"duplicate record_id in queue: {record_id}")
            if not _is_sha256(row["input_sha256"]):
                raise ValueError(f"invalid input_sha256 for {record_id}")
            seen.add(record_id)
            yield row


def load_queue(path: Path) -> list[dict[str, Any]]:
    return list(iter_queue(path))


def _validate_records(records: Iterable[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for index, record in enumerate(records, 1):
        record_id = str(record.get("record_id") or "").strip()
        if not record_id:
            raise ValueError(f"record_id is required at queue index {index}")
        if record_id in seen:
            raise ValueError(f"duplicate record_id in queue: {record_id}")
        if not _is_sha256(record.get("input_sha256")):
            raise ValueError(f"invalid input_sha256 for {record_id}")
        seen.add(record_id)


def split_records(
    records: list[dict[str, Any]], *, max_batch_requests: int = MAX_BATCH_REQUESTS
) -> list[list[dict[str, Any]]]:
    if not 1 <= max_batch_requests <= MAX_BATCH_REQUESTS:
        raise ValueError(f"max_batch_requests must be between 1 and {MAX_BATCH_REQUESTS}")
    _validate_records(records)
    return [
        records[start : start + max_batch_requests]
        for start in range(0, len(records), max_batch_requests)
    ]


def bulk_review_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["record_id", "decisions"],
        "properties": {
            "record_id": {"type": "string", "minLength": 1},
            "decisions": {
                "type": "array",
                "minItems": 4,
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["scope", "status", "rationale", "patch"],
                    "properties": {
                        "scope": {"enum": list(REVIEW_SCOPES)},
                        "status": {"enum": sorted(DECISION_STATUSES)},
                        "rationale": {"type": "string", "minLength": 1},
                        "patch": {"type": "object"},
                    },
                },
            },
        },
    }


def build_batch_request(record: dict[str, Any], *, model: str = DEFAULT_MODEL) -> dict[str, Any]:
    """Build future-provider request material; this function performs no I/O."""
    record = ensure_input_sha256(record)
    policy = (
        "Review one deterministic Japanese semantic-data record. Return exactly four "
        "judgments: semantic, pragmatic, task, external_action. Never invent evidence "
        "or overwrite source-owned meaning candidates.\nRECORD=" + _json_line(record)
    )
    return {
        "custom_id": str(record["record_id"]),
        "method": "POST",
        "url": BATCH_ENDPOINT,
        "body": {
            "model": model,
            "input": policy,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "bulk_review_decisions",
                    "schema": bulk_review_output_schema(),
                    "strict": True,
                }
            },
        },
    }


def _job_id(records: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for source in records:
        record = ensure_input_sha256(source)
        digest.update(str(record["record_id"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(record["input_sha256"]).encode("ascii"))
        digest.update(b"\n")
    return f"bulk-review-{digest.hexdigest()[:20]}"


def prepare_bulk_review_job(
    records: list[dict[str, Any]],
    output_root: Path,
    *,
    max_batch_requests: int = MAX_BATCH_REQUESTS,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Prepare future-provider request files only; never performs network I/O."""
    records = [ensure_input_sha256(record) for record in records]
    chunks = split_records(records, max_batch_requests=max_batch_requests)
    root = output_root / "bulk-review"
    request_root = root / "requests"
    request_root.mkdir(parents=True, exist_ok=True)
    batches: list[dict[str, Any]] = []
    for number, chunk in enumerate(chunks, 1):
        requests = [build_batch_request(record, model=model) for record in chunk]
        text = "".join(_json_line(item) + "\n" for item in requests)
        path = request_root / f"batch-{number:04d}.jsonl"
        path.write_text(text, encoding="utf-8", newline="\n")
        batches.append(
            {
                "provider_batch_index": number,
                "request_count": len(requests),
                "path": str(path.relative_to(output_root)),
                "sha256": _sha256_bytes(text.encode("utf-8")),
            }
        )
    manifest = {
        "schema_version": "1.1.0",
        "bulk_review_job_id": _job_id(records),
        "status": "prepared",
        "total_records": len(records),
        "provider_batch_limit": max_batch_requests,
        "provider_batch_count": len(batches),
        "provider_batches": batches,
        "endpoint": BATCH_ENDPOINT,
        "model": model,
        "structured_outputs": True,
        "decision_scopes": list(REVIEW_SCOPES),
        "runtime_promotion_allowed": False,
        "network_call_performed": False,
    }
    (root / "bulk_review_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


def _retry(operation: Callable[[], T], *, attempts: int = 3) -> T:
    last: Exception | None = None
    for _ in range(attempts):
        try:
            return operation()
        except OSError as exc:
            last = exc
    assert last is not None
    raise last


def _validate_patch(patch: Any) -> dict[str, Any]:
    if patch is None:
        return {}
    if not isinstance(patch, dict):
        raise ValueError("decision patch must be an object")
    unknown = set(patch) - PATCH_FIELDS
    if unknown:
        raise ValueError(f"decision patch contains forbidden fields: {sorted(unknown)}")
    if "polarity" in patch and patch["polarity"] not in {"positive", "negative", "neutral"}:
        raise ValueError("invalid polarity")
    intensity = patch.get("intensity")
    if "intensity" in patch and (
        isinstance(intensity, bool)
        or not isinstance(intensity, (int, float))
        or not 0.0 <= float(intensity) <= 1.0
    ):
        raise ValueError("invalid intensity")
    if "task_candidates" in patch and not isinstance(patch["task_candidates"], list):
        raise ValueError("task_candidates must be a list")
    if "external_action_risk" in patch and not isinstance(patch["external_action_risk"], bool):
        raise ValueError("external_action_risk must be a boolean")
    return patch


def validate_decision_entry(decision: dict[str, Any]) -> None:
    required = (
        "decision_id", "record_id", "scope", "status", "reviewer",
        "decided_at", "rationale", "input_sha256",
    )
    missing = [key for key in required if not str(decision.get(key) or "").strip()]
    if missing:
        raise ValueError(f"decision fields missing: {missing}")
    if decision["scope"] not in REVIEW_SCOPES:
        raise ValueError(f"invalid decision scope: {decision['scope']}")
    if decision["status"] not in DECISION_STATUSES:
        raise ValueError(f"invalid decision status: {decision['status']}")
    if not _is_sha256(decision["input_sha256"]):
        raise ValueError("invalid input_sha256")
    _validate_patch(decision.get("patch") or {})


def _extract_response_payload(result: dict[str, Any]) -> dict[str, Any]:
    if "decisions" in result:
        return result
    body = (result.get("response") or {}).get("body") or {}
    if isinstance(body.get("output_text"), str):
        return json.loads(body["output_text"])
    raise ValueError(f"structured payload missing for {result.get('custom_id')}")


def merge_batch_results(
    records: list[dict[str, Any]],
    result_rows: Iterable[dict[str, Any]],
    output_root: Path,
    *,
    reviewer: str = "review-provider",
    decided_at: str | None = None,
) -> dict[str, Any]:
    records = [ensure_input_sha256(record) for record in records]
    _validate_records(records)
    by_id = {str(record["record_id"]): record for record in records}
    payload_by_id: dict[str, dict[str, Any]] = {}
    for row in result_rows:
        custom_id = str(row.get("custom_id") or row.get("record_id") or "").strip()
        if not custom_id:
            raise ValueError("result row is missing custom_id")
        if custom_id in payload_by_id:
            raise ValueError(f"duplicate result custom_id: {custom_id}")
        if custom_id not in by_id:
            raise ValueError(f"result references unknown record: {custom_id}")
        payload = _extract_response_payload(row)
        if str(payload.get("record_id") or "") != custom_id:
            raise ValueError(f"result record_id mismatch for {custom_id}")
        payload_by_id[custom_id] = payload
    missing = sorted(set(by_id) - set(payload_by_id))
    if missing:
        raise ValueError(f"missing review results: {missing[:20]}")

    timestamp = decided_at or DEFAULT_DECIDED_AT
    job_id = _job_id(records)
    decisions: list[dict[str, Any]] = []
    for record in records:
        rid = str(record["record_id"])
        items = payload_by_id[rid].get("decisions")
        if not isinstance(items, list) or len(items) != 4:
            raise ValueError(f"exactly four decisions are required for {rid}")
        scope_map = {item["scope"]: item for item in items}
        if set(scope_map) != set(REVIEW_SCOPES):
            raise ValueError(f"scope coverage mismatch for {rid}")
        for scope in REVIEW_SCOPES:
            item = scope_map[scope]
            patch = _validate_patch(item.get("patch") or {})
            decision = {
                "decision_id": f"{job_id}:{rid}:{scope}",
                "record_id": rid,
                "scope": scope,
                "status": item["status"],
                "reviewer": reviewer,
                "decided_at": timestamp,
                "rationale": str(item["rationale"]),
                "input_sha256": record["input_sha256"],
            }
            if patch:
                decision["patch"] = patch
            validate_decision_entry(decision)
            decisions.append(decision)

    root = output_root / "bulk-review"
    root.mkdir(parents=True, exist_ok=True)
    ledger = root / "decision_ledger.jsonl"
    text = "".join(_json_line(item) + "\n" for item in decisions)
    ledger.write_text(text, encoding="utf-8", newline="\n")
    summary = {
        "schema_version": "1.0.0",
        "bulk_review_job_id": job_id,
        "status": "completed",
        "total_records": len(records),
        "success_records": len(records),
        "error_records": 0,
        "decision_count": len(decisions),
        "decision_ledger_path": str(ledger.relative_to(output_root)),
        "decision_ledger_sha256": _sha256_bytes(text.encode("utf-8")),
    }
    (root / "bulk_review_manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def execute_with_provider(
    records: list[dict[str, Any]],
    output_root: Path,
    provider: ReviewProvider,
    *,
    max_batch_requests: int = MAX_BATCH_REQUESTS,
    model: str = DEFAULT_MODEL,
    retry_attempts: int = 3,
    decided_at: str | None = None,
) -> dict[str, Any]:
    records = [ensure_input_sha256(record) for record in records]
    prepare_bulk_review_job(records, output_root, max_batch_requests=max_batch_requests, model=model)
    results: list[dict[str, Any]] = []
    for chunk in split_records(records, max_batch_requests=max_batch_requests):
        requests = [build_batch_request(record, model=model) for record in chunk]
        results.extend(
            _retry(lambda requests=requests: provider.review_batch(requests), attempts=retry_attempts)
        )
    return merge_batch_results(records, results, output_root, decided_at=decided_at)


def load_review_rules(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ValueError("review rules must be a mapping")
    return value


def load_provider_config(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ValueError("provider config must be a mapping")
    return value


def _meaning_text(record: dict[str, Any]) -> str:
    values: list[str] = []
    for candidate in record.get("meaning_candidates") or []:
        if not isinstance(candidate, dict):
            continue
        for key in ("meaning", "label"):
            if candidate.get(key):
                values.append(str(candidate[key]))
        values.extend(str(item) for item in candidate.get("glosses") or [])
    return " ".join(values).casefold()


def _evidence_text(record: dict[str, Any]) -> str:
    values = [_meaning_text(record)]
    values.extend(str(item) for item in record.get("usage_labels") or [])
    values.extend(str(item) for item in record.get("part_of_speech") or [])
    return " ".join(values).casefold()


def _surface(record: dict[str, Any]) -> str:
    values = record.get("surfaces") or [record.get("lemma") or record.get("record_id")]
    return str(values[0])


@dataclass
class ChatGPTAppProvider:
    """No-network provider applying rules established from ChatGPT app review."""

    rules: dict[str, Any]
    provider_name: str = "chatgpt_app"

    def review_batch(self, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        raise RuntimeError(
            "ChatGPTAppProvider does not consume external-provider request batches; "
            "use review_record/review_queue_rule_based"
        )

    def _evidence_state(self, record: dict[str, Any]) -> tuple[bool, str]:
        policy = self.rules["review_policy"]
        text = _evidence_text(record)
        license_text = str((record.get("source") or {}).get("license") or "").casefold()
        if any(str(item).casefold() in license_text for item in policy["pending_license_markers"]):
            return False, "source/license evidence pending"
        if any(str(item).casefold() in text for item in policy["placeholder_markers"]):
            return False, "meaning evidence placeholder"
        if any(str(item).casefold() in text for item in policy.get("ambiguous_markers", [])):
            return False, "meaning candidate remains ambiguous"
        return True, "source meaning evidence present"

    @staticmethod
    def _marker_matches(text: str, marker: str) -> bool:
        marker = marker.casefold().strip()
        if not marker:
            return False
        if marker.isascii() and any(ch.isalpha() for ch in marker):
            return re.search(
                r"(?<![a-z0-9_])" + re.escape(marker) + r"(?![a-z0-9_])", text
            ) is not None
        return marker in text

    def _polarity(self, record: dict[str, Any]) -> tuple[str, float]:
        policy = self.rules["review_policy"]
        text = _meaning_text(record)
        positive = any(self._marker_matches(text, str(item)) for item in policy["positive_markers"])
        negative = any(self._marker_matches(text, str(item)) for item in policy["negative_markers"])
        semantic = self.rules["scope_rules"]["semantic"]
        if positive ^ negative:
            return (
                "positive" if positive else "negative",
                float(semantic["explicit_polarity_intensity"]),
            )
        return str(semantic["default_polarity"]), float(semantic["default_intensity"])

    def _pragmatic(self, record: dict[str, Any]) -> tuple[str, str, bool]:
        feature = str(record.get("feature_type") or "")
        source_kind = str(record.get("source_kind") or "")
        sufficient, why = self._evidence_state(record)
        rules = self.rules["scope_rules"]["pragmatic"]
        if source_kind == "open_lexicon" or not feature:
            return str(rules["open_lexicon_status"]), "lexicon-only context is source-defined", True
        if not sufficient:
            return str(rules["insufficient_evidence_status"]), why, False
        markers = [
            str(item).casefold()
            for item in self.rules.get("pragmatic_feature_evidence", {}).get(feature, [])
        ]
        text = _evidence_text(record) + " " + _surface(record).casefold()
        matched = any(marker in text for marker in markers)
        if matched:
            return str(rules["feature_match_status"]), f"{feature} evidence matched source usage/context", True
        return (
            str(rules["feature_mismatch_status"]),
            f"lexical context usable; {feature} feature evidence not established",
            False,
        )

    def review_record(self, record: dict[str, Any]) -> dict[str, Any]:
        record = ensure_input_sha256(record)
        feature = str(record.get("feature_type") or "")
        sufficient, semantic_why = self._evidence_state(record)
        semantic_rules = self.rules["scope_rules"]["semantic"]
        semantic_status = str(
            semantic_rules["sufficient_evidence_status"]
            if sufficient
            else semantic_rules["insufficient_evidence_status"]
        )
        polarity, intensity = self._polarity(record)
        semantic_patch: dict[str, Any] = {"polarity": polarity, "intensity": intensity}
        pragmatic_status, pragmatic_why, feature_supported = self._pragmatic(record)
        targets = record.get("semantic_targets") or []
        if feature and not feature_supported and sufficient and "language_feature" in targets:
            semantic_patch["semantic_targets"] = [
                target for target in targets if target != "language_feature"
            ]

        evidence = _evidence_text(record)
        social = [
            marker
            for marker in (
                "kansai", "kagoshima", "kyūshū", "shikoku", "chūgoku",
                "tsugaru", "akita", "nagoya", "tohoku", "hokkaido",
                "polite", "humble", "informal",
            )
            if marker in evidence
        ]
        surface = _surface(record)
        context_patch = {
            "context_conditions": {
                "required_any": [],
                "required_all": [],
                "forbidden_any": [],
                "required_social": social,
                "required_discourse": [f"feature:{feature}"]
                if feature and feature_supported and pragmatic_status == "approved"
                else [],
            },
            "examples": {
                "positive": [f"「{surface}」をSource提示の意味で用いる文脈。"],
                "negative": [f"「{surface}」という文字列を引用するだけの文脈。"],
                "boundary": [f"「{surface}」の意味・機能を一意に特定できない文脈。"],
            },
        }

        action_risk = str(record.get("risk_class") or "") in set(
            self.rules["scope_rules"]["external_action"]["risk_true_when_risk_class"]
        )
        task_rules = self.rules["scope_rules"]["task"]
        task_status = str(
            task_rules["action_sensitive_status"] if action_risk else task_rules["default_status"]
        )
        task_patch: dict[str, Any] = {} if action_risk else {"task_candidates": []}
        return {
            "record_id": str(record["record_id"]),
            "decisions": [
                {
                    "scope": "semantic",
                    "status": semantic_status,
                    "rationale": semantic_why,
                    "patch": semantic_patch,
                },
                {
                    "scope": "pragmatic",
                    "status": pragmatic_status,
                    "rationale": pragmatic_why,
                    "patch": context_patch,
                },
                {
                    "scope": "task",
                    "status": task_status,
                    "rationale": (
                        "action-sensitive語は文・発話行為なしではTask確定不可"
                        if action_risk
                        else "語単独では実行Taskを表さない"
                    ),
                    "patch": task_patch,
                },
                {
                    "scope": "external_action",
                    "status": str(self.rules["scope_rules"]["external_action"]["status"]),
                    "rationale": (
                        "action-sensitive evidence; downstream guard required"
                        if action_risk
                        else "語単独の外部操作Riskなし"
                    ),
                    "patch": {"external_action_risk": action_risk},
                },
            ],
        }


@dataclass
class OpenAIAPIProvider:
    """Future external API entry. Deliberately non-operational in Phase 1-4."""

    provider_name: str = "openai_api"

    def review_batch(self, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        raise NotImplementedError(
            "OpenAIAPIProvider is a Phase 1-4 stub; external API calls are disabled"
        )


def create_provider(config: dict[str, Any], rules: dict[str, Any]) -> ReviewProvider:
    provider = str(config.get("provider") or "chatgpt_app")
    if provider == "chatgpt_app":
        return ChatGPTAppProvider(rules)
    if provider == "openai_api":
        return OpenAIAPIProvider()
    raise ValueError(f"unknown review provider: {provider}")


def review_queue_rule_based(
    queue_path: Path,
    ledger_path: Path,
    manifest_path: Path,
    *,
    config_path: Path,
    rules_path: Path,
    decided_at: str = DEFAULT_DECIDED_AT,
) -> dict[str, Any]:
    config = load_provider_config(config_path)
    rules = load_review_rules(rules_path)
    provider = create_provider(config, rules)
    if not isinstance(provider, ChatGPTAppProvider):
        raise RuntimeError("Phase 1-4 execution requires provider: chatgpt_app")

    actual_sha = _sha256_file(queue_path)
    expected_sha = str(rules.get("source_queue", {}).get("sha256") or "")
    if expected_sha and expected_sha != actual_sha:
        raise ValueError(f"fixed queue SHA mismatch: {actual_sha}")
    sample_ids = set(rules.get("source_queue", {}).get("sample_record_ids") or [])

    status_counts: Counter[str] = Counter()
    scope_counts: Counter[str] = Counter()
    reviewer_counts: Counter[str] = Counter()
    total = decision_count = 0
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("w", encoding="utf-8", newline="\n") as out:
        for record in iter_queue(queue_path):
            total += 1
            payload = provider.review_record(record)
            reviewer = (
                "gpt-app-sample-review"
                if record["record_id"] in sample_ids
                else "gpt-app-rule-based-review"
            )
            reviewer_counts[reviewer] += 4
            for item in payload["decisions"]:
                scope = str(item["scope"])
                status = str(item["status"])
                entry = {
                    "decision_id": f"P14-{record['record_id']}-{scope}",
                    "record_id": record["record_id"],
                    "scope": scope,
                    "status": status,
                    "reviewer": reviewer,
                    "decided_at": decided_at,
                    "rationale": str(item["rationale"]),
                    "input_sha256": record["input_sha256"],
                }
                patch = _validate_patch(item.get("patch") or {})
                if patch:
                    entry["patch"] = patch
                validate_decision_entry(entry)
                out.write(_json_line(entry) + "\n")
                decision_count += 1
                status_counts[status] += 1
                scope_counts[scope] += 1

    ledger_bytes = ledger_path.stat().st_size
    summary = {
        "schema_version": "1.0.0",
        "provider": "chatgpt_app",
        "review_method": "rule_based",
        "sample_method": "chatgpt_app_review_100",
        "network_call_performed": False,
        "external_api_enabled": False,
        "external_api_provider": "openai_api_stub",
        "queue_path": str(rules.get("source_queue", {}).get("path") or queue_path.name),
        "queue_sha256": actual_sha,
        "total_records": total,
        "sample_review_records": len(sample_ids),
        "rule_applied_records": total - len(sample_ids),
        "decision_count": decision_count,
        "decision_scope_counts": dict(sorted(scope_counts.items())),
        "decision_status_counts": dict(sorted(status_counts.items())),
        "reviewer_counts": dict(sorted(reviewer_counts.items())),
        "rules_sha256": _sha256_file(rules_path),
        "decision_ledger_path": str(ledger_path),
        "decision_ledger_sha256": _sha256_file(ledger_path),
        "decision_ledger_bytes": ledger_bytes,
        "storage_status": (
            "generated-local; GitHub regular-file publish blocked (>100 MiB)"
            if ledger_bytes > 100 * 1024 * 1024
            else "generated-local; GitHub regular-file publishable"
        ),
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return summary


def _main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    review = sub.add_parser("review")
    review.add_argument("--queue", type=Path, required=True)
    review.add_argument("--ledger", type=Path, required=True)
    review.add_argument("--manifest", type=Path, required=True)
    review.add_argument("--config", type=Path, default=Path("config/review_provider.yaml"))
    review.add_argument("--rules", type=Path, default=Path("rules/review_rules.yaml"))
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--queue", type=Path, required=True)
    prepare.add_argument("--output-root", type=Path, required=True)
    prepare.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()
    result = (
        review_queue_rule_based(
            args.queue,
            args.ledger,
            args.manifest,
            config_path=args.config,
            rules_path=args.rules,
        )
        if args.command == "review"
        else prepare_bulk_review_job(load_queue(args.queue), args.output_root, model=args.model)
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
