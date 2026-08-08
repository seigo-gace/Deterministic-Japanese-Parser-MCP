#!/usr/bin/env python3
"""Build-time Bulk Review Station for the fixed semantic review queue.

The station is deliberately outside ``tools/unified_semantic_data`` so the
runtime/data compiler remains non-AI.  ``prepare`` is deterministic and makes
no network calls.  ``submit``/``collect`` are explicit operator actions.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import time
from typing import Any, Callable, Iterable, Protocol, TypeVar
from urllib import error as urlerror
from urllib import request as urlrequest
import uuid

MAX_BATCH_REQUESTS = 50_000
OPENAI_API_BASE = "https://api.openai.com"
BATCH_ENDPOINT = "/v1/responses"
REVIEW_SCOPES = ("semantic", "pragmatic", "task", "external_action")
DECISION_STATUSES = {"approved", "needs-evidence", "rejected", "hold"}
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
    "polarity",
    "intensity",
    "task_candidates",
    "external_action_risk",
}
DEFAULT_MODEL = os.environ.get("OPENAI_REVIEW_MODEL", "gpt-5-mini")

T = TypeVar("T")


class ReviewProvider(Protocol):
    def review_batch(self, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return provider-style result rows for one internal batch."""


def _json_line(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_queue(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"queue row must be an object: {path}:{line_number}")
        rows.append(row)
    _validate_records(rows)
    return rows


def _validate_records(records: Iterable[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for index, record in enumerate(records, 1):
        record_id = str(record.get("record_id") or "").strip()
        input_sha256 = str(record.get("input_sha256") or "").strip()
        if not record_id:
            raise ValueError(f"record_id is required at queue index {index}")
        if record_id in seen:
            raise ValueError(f"duplicate record_id in queue: {record_id}")
        if len(input_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in input_sha256.lower()):
            raise ValueError(f"invalid input_sha256 for {record_id}")
        seen.add(record_id)


def split_records(
    records: list[dict[str, Any]], *, max_batch_requests: int = MAX_BATCH_REQUESTS
) -> list[list[dict[str, Any]]]:
    if max_batch_requests < 1 or max_batch_requests > MAX_BATCH_REQUESTS:
        raise ValueError(
            f"max_batch_requests must be between 1 and {MAX_BATCH_REQUESTS}"
        )
    _validate_records(records)
    return [
        records[start : start + max_batch_requests]
        for start in range(0, len(records), max_batch_requests)
    ]


def bulk_review_output_schema() -> dict[str, Any]:
    patch_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "meaning_candidates": {"type": "array", "items": {"type": "object"}},
            "parameters": {"type": "object"},
            "register": {"type": "object"},
            "context_conditions": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "required_any": {"type": "array"},
                    "required_all": {"type": "array"},
                    "forbidden_any": {"type": "array"},
                    "required_social": {"type": "array"},
                    "required_discourse": {"type": "array"},
                },
            },
            "examples": {"type": "object"},
            "domains": {"type": "array"},
            "usage_labels": {"type": "array"},
            "semantic_targets": {"type": "array"},
            "risk_class": {"type": "string"},
            "polarity": {"enum": ["positive", "negative", "neutral"]},
            "intensity": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "task_candidates": {"type": "array"},
            "external_action_risk": {"type": "boolean"},
        },
    }
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
                        "patch": patch_schema,
                    },
                },
            },
        },
    }


def _review_policy(record: dict[str, Any]) -> str:
    return (
        "Review this one deterministic Japanese semantic-data record. "
        "Return exactly four judgments: semantic, pragmatic, task, and external_action. "
        "Use approved only when the supplied evidence is sufficient. Otherwise use "
        "needs-evidence, hold, or rejected. Never invent evidence. Never rewrite "
        "source-owned JMdict meaning_candidates. Return only the structured result.\n"
        f"RECORD={_json_line(record)}"
    )


def build_batch_request(
    record: dict[str, Any], *, model: str = DEFAULT_MODEL
) -> dict[str, Any]:
    record_id = str(record["record_id"])
    return {
        "custom_id": record_id,
        "method": "POST",
        "url": BATCH_ENDPOINT,
        "body": {
            "model": model,
            "input": _review_policy(record),
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
    for record in records:
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
    """Create deterministic provider request files; no API call is made."""
    chunks = split_records(records, max_batch_requests=max_batch_requests)
    job_id = _job_id(records)
    root = output_root / "bulk-review"
    request_root = root / "requests"
    request_root.mkdir(parents=True, exist_ok=True)

    provider_batches: list[dict[str, Any]] = []
    for number, chunk in enumerate(chunks, 1):
        requests = [build_batch_request(record, model=model) for record in chunk]
        text = "".join(_json_line(item) + "\n" for item in requests)
        path = request_root / f"batch-{number:04d}.jsonl"
        path.write_text(text, encoding="utf-8", newline="\n")
        provider_batches.append(
            {
                "provider_batch_index": number,
                "request_count": len(requests),
                "path": str(path.relative_to(output_root)),
                "sha256": _sha256_bytes(text.encode("utf-8")),
                "first_custom_id": requests[0]["custom_id"] if requests else None,
                "last_custom_id": requests[-1]["custom_id"] if requests else None,
            }
        )

    manifest = {
        "schema_version": "1.0.0",
        "bulk_review_job_id": job_id,
        "status": "prepared",
        "total_records": len(records),
        "provider_batch_limit": max_batch_requests,
        "provider_batch_count": len(provider_batches),
        "provider_batches": provider_batches,
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


def _retry(
    operation: Callable[[], T], *, attempts: int = 3, initial_delay: float = 1.0
) -> T:
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    delay = initial_delay
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except (OSError, TimeoutError, urlerror.URLError, urlerror.HTTPError) as exc:
            last_error = exc
            if attempt == attempts:
                break
            time.sleep(delay)
            delay *= 2
    assert last_error is not None
    raise last_error


def _extract_response_payload(result: dict[str, Any]) -> dict[str, Any]:
    if "decisions" in result:
        return result
    response = result.get("response") or {}
    if response.get("status_code") not in (None, 200):
        raise ValueError(
            f"provider response failed for {result.get('custom_id')}: "
            f"HTTP {response.get('status_code')}"
        )
    body = response.get("body") or {}
    if isinstance(body.get("output_text"), str):
        return json.loads(body["output_text"])
    for output in body.get("output", []):
        if not isinstance(output, dict):
            continue
        for content in output.get("content", []):
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                return json.loads(text)
    raise ValueError(f"structured payload missing for {result.get('custom_id')}")


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
    if "intensity" in patch and (
        isinstance(patch["intensity"], bool)
        or not isinstance(patch["intensity"], (int, float))
        or not 0.0 <= float(patch["intensity"]) <= 1.0
    ):
        raise ValueError("invalid intensity")
    if "context_conditions" in patch and not isinstance(patch["context_conditions"], dict):
        raise ValueError("context_conditions must be an object")
    if "task_candidates" in patch and not isinstance(patch["task_candidates"], list):
        raise ValueError("task_candidates must be a list")
    if "external_action_risk" in patch and not isinstance(patch["external_action_risk"], bool):
        raise ValueError("external_action_risk must be a boolean")
    return patch


def validate_decision_entry(decision: dict[str, Any]) -> None:
    required = (
        "decision_id",
        "record_id",
        "scope",
        "status",
        "reviewer",
        "decided_at",
        "rationale",
        "input_sha256",
    )
    missing = [key for key in required if not str(decision.get(key) or "").strip()]
    if missing:
        raise ValueError(f"decision fields missing: {missing}")
    if decision["scope"] not in REVIEW_SCOPES:
        raise ValueError(f"invalid decision scope: {decision['scope']}")
    if decision["status"] not in DECISION_STATUSES:
        raise ValueError(f"invalid decision status: {decision['status']}")
    digest = str(decision["input_sha256"])
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest.lower()):
        raise ValueError("invalid input_sha256")
    _validate_patch(decision.get("patch") or {})


def merge_batch_results(
    records: list[dict[str, Any]],
    result_rows: Iterable[dict[str, Any]],
    output_root: Path,
    *,
    reviewer: str = "openai-batch-review",
    decided_at: str | None = None,
) -> dict[str, Any]:
    """Merge provider results by custom_id/record_id and emit Decision Ledger."""
    _validate_records(records)
    by_id = {str(record["record_id"]): record for record in records}
    payload_by_id: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for row in result_rows:
        custom_id = str(row.get("custom_id") or row.get("record_id") or "").strip()
        if not custom_id:
            raise ValueError("result row is missing custom_id")
        if custom_id in payload_by_id:
            raise ValueError(f"duplicate result custom_id: {custom_id}")
        if custom_id not in by_id:
            raise ValueError(f"result references unknown record: {custom_id}")
        if row.get("error"):
            errors.append(custom_id)
            continue
        payload = _extract_response_payload(row)
        if str(payload.get("record_id") or "") != custom_id:
            raise ValueError(f"result record_id mismatch for {custom_id}")
        payload_by_id[custom_id] = payload

    missing = sorted(set(by_id) - set(payload_by_id) - set(errors))
    if missing:
        raise ValueError(f"missing review results: {missing[:20]}")

    timestamp = decided_at or datetime.now(timezone.utc).isoformat()
    job_id = _job_id(records)
    decisions: list[dict[str, Any]] = []
    hold_records: set[str] = set(errors)
    for record in records:
        record_id = str(record["record_id"])
        if record_id in errors:
            continue
        payload = payload_by_id[record_id]
        items = payload.get("decisions")
        if not isinstance(items, list) or len(items) != 4:
            raise ValueError(f"exactly four decisions are required for {record_id}")
        scopes = [str(item.get("scope") or "") for item in items if isinstance(item, dict)]
        if sorted(scopes) != sorted(REVIEW_SCOPES):
            raise ValueError(f"scope coverage mismatch for {record_id}: {scopes}")
        if len(set(scopes)) != 4:
            raise ValueError(f"duplicate scope result for {record_id}")
        scope_map = {item["scope"]: item for item in items}
        for scope in REVIEW_SCOPES:
            item = scope_map[scope]
            status = str(item.get("status") or "")
            rationale = str(item.get("rationale") or "").strip()
            if status not in DECISION_STATUSES or not rationale:
                raise ValueError(f"invalid review result for {record_id}/{scope}")
            patch = _validate_patch(item.get("patch") or {})
            decision = {
                "decision_id": f"{job_id}:{record_id}:{scope}",
                "record_id": record_id,
                "scope": scope,
                "status": status,
                "reviewer": reviewer,
                "decided_at": timestamp,
                "rationale": rationale,
                "input_sha256": record["input_sha256"],
            }
            if patch:
                decision["patch"] = patch
            validate_decision_entry(decision)
            decisions.append(decision)
            if status != "approved":
                hold_records.add(record_id)

    ledger_root = output_root / "bulk-review"
    ledger_root.mkdir(parents=True, exist_ok=True)
    ledger_path = ledger_root / "decision_ledger.jsonl"
    ledger_text = "".join(_json_line(item) + "\n" for item in decisions)
    ledger_path.write_text(ledger_text, encoding="utf-8", newline="\n")

    summary = {
        "schema_version": "1.0.0",
        "bulk_review_job_id": job_id,
        "status": "completed" if not errors else "completed-with-errors",
        "total_records": len(records),
        "success_records": len(payload_by_id),
        "hold_records": len(hold_records),
        "error_records": len(errors),
        "decision_count": len(decisions),
        "decision_ledger_path": str(ledger_path.relative_to(output_root)),
        "decision_ledger_sha256": _sha256_bytes(ledger_text.encode("utf-8")),
    }
    (ledger_root / "bulk_review_manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
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
    """Synchronous abstraction used for local/mocked verification."""
    prepare_bulk_review_job(
        records,
        output_root,
        max_batch_requests=max_batch_requests,
        model=model,
    )
    all_results: list[dict[str, Any]] = []
    for chunk in split_records(records, max_batch_requests=max_batch_requests):
        requests = [build_batch_request(record, model=model) for record in chunk]
        results = _retry(
            lambda requests=requests: provider.review_batch(requests),
            attempts=retry_attempts,
            initial_delay=0.01,
        )
        all_results.extend(results)
    return merge_batch_results(
        records,
        all_results,
        output_root,
        decided_at=decided_at,
    )


@dataclass
class OpenAIBatchClient:
    """Minimal stdlib Batch API client; no OpenAI SDK dependency is required."""

    api_key: str
    base_url: str = OPENAI_API_BASE
    timeout: float = 60.0
    retry_attempts: int = 3

    @classmethod
    def from_environment(cls) -> "OpenAIBatchClient":
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for submit/collect")
        return cls(api_key=api_key)

    def _request_json(
        self, method: str, path: str, *, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if data is not None:
            headers["Content-Type"] = "application/json"

        def operation() -> dict[str, Any]:
            req = urlrequest.Request(
                f"{self.base_url}{path}", data=data, headers=headers, method=method
            )
            with urlrequest.urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))

        return _retry(operation, attempts=self.retry_attempts)

    def upload_batch_file(self, path: Path) -> str:
        boundary = f"----djpmcp-{uuid.uuid4().hex}"
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        payload = path.read_bytes()
        body = b"".join(
            [
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"purpose\"\r\n\r\nbatch\r\n".encode(),
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\nContent-Type: {mime}\r\n\r\n".encode(),
                payload,
                f"\r\n--{boundary}--\r\n".encode(),
            ]
        )
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }

        def operation() -> dict[str, Any]:
            req = urlrequest.Request(
                f"{self.base_url}/v1/files", data=body, headers=headers, method="POST"
            )
            with urlrequest.urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))

        result = _retry(operation, attempts=self.retry_attempts)
        return str(result["id"])

    def create_batch(self, input_file_id: str) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/v1/batches",
            payload={
                "input_file_id": input_file_id,
                "endpoint": BATCH_ENDPOINT,
                "completion_window": "24h",
            },
        )

    def get_batch(self, batch_id: str) -> dict[str, Any]:
        return self._request_json("GET", f"/v1/batches/{batch_id}")

    def download_file_content(self, file_id: str) -> bytes:
        headers = {"Authorization": f"Bearer {self.api_key}"}

        def operation() -> bytes:
            req = urlrequest.Request(
                f"{self.base_url}/v1/files/{file_id}/content",
                headers=headers,
                method="GET",
            )
            with urlrequest.urlopen(req, timeout=self.timeout) as response:
                return response.read()

        return _retry(operation, attempts=self.retry_attempts)


def submit_prepared_job(output_root: Path, client: OpenAIBatchClient) -> dict[str, Any]:
    manifest_path = output_root / "bulk-review" / "bulk_review_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    submitted: list[dict[str, Any]] = []
    for item in manifest.get("provider_batches", []):
        request_path = output_root / item["path"]
        input_file_id = client.upload_batch_file(request_path)
        batch = client.create_batch(input_file_id)
        submitted.append(
            {
                **item,
                "input_file_id": input_file_id,
                "openai_batch_id": batch["id"],
                "openai_status": batch.get("status"),
            }
        )
    manifest["status"] = "submitted"
    manifest["provider_batches"] = submitted
    manifest["network_call_performed"] = True
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


def collect_submitted_job(
    records: list[dict[str, Any]],
    output_root: Path,
    client: OpenAIBatchClient,
) -> dict[str, Any]:
    manifest_path = output_root / "bulk-review" / "bulk_review_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    result_rows: list[dict[str, Any]] = []
    for item in manifest.get("provider_batches", []):
        batch_id = item.get("openai_batch_id")
        if not batch_id:
            raise RuntimeError("prepared batch has not been submitted")
        batch = client.get_batch(batch_id)
        if batch.get("status") != "completed":
            raise RuntimeError(f"batch {batch_id} is not completed: {batch.get('status')}")
        output_file_id = batch.get("output_file_id")
        if not output_file_id:
            raise RuntimeError(f"batch {batch_id} has no output_file_id")
        content = client.download_file_content(output_file_id).decode("utf-8")
        for line in content.splitlines():
            if line.strip():
                result_rows.append(json.loads(line))
    return merge_batch_results(records, result_rows, output_root)


def _main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare")
    prepare.add_argument("--queue", type=Path, required=True)
    prepare.add_argument("--output-root", type=Path, required=True)
    prepare.add_argument("--model", default=DEFAULT_MODEL)

    submit = sub.add_parser("submit")
    submit.add_argument("--output-root", type=Path, required=True)

    collect = sub.add_parser("collect")
    collect.add_argument("--queue", type=Path, required=True)
    collect.add_argument("--output-root", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare_bulk_review_job(
            load_queue(args.queue), args.output_root, model=args.model
        )
    elif args.command == "submit":
        result = submit_prepared_job(
            args.output_root, OpenAIBatchClient.from_environment()
        )
    else:
        result = collect_submitted_job(
            load_queue(args.queue),
            args.output_root,
            OpenAIBatchClient.from_environment(),
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
