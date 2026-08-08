from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Literal

import pytest
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from bulk_review_station import (  # noqa: E402
    MAX_BATCH_REQUESTS,
    REVIEW_SCOPES,
    build_batch_request,
    execute_with_provider,
    merge_batch_results,
    prepare_bulk_review_job,
    split_records,
)


class ContextConditionsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    required_any: list[Any] | None = None
    required_all: list[Any] | None = None
    forbidden_any: list[Any] | None = None
    required_social: list[Any] | None = None
    required_discourse: list[Any] | None = None


class PatchModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    meaning_candidates: list[dict[str, Any]] | None = None
    parameters: dict[str, Any] | None = None
    register_value: dict[str, Any] | None = Field(default=None, alias="register")
    context_conditions: ContextConditionsModel | None = None
    examples: dict[str, Any] | None = None
    domains: list[Any] | None = None
    usage_labels: list[Any] | None = None
    semantic_targets: list[Any] | None = None
    risk_class: str | None = None
    polarity: Literal["positive", "negative", "neutral"] | None = None
    intensity: float | None = Field(default=None, ge=0.0, le=1.0)
    task_candidates: list[Any] | None = None
    external_action_risk: bool | None = None


class LedgerModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision_id: str = Field(min_length=1)
    record_id: str = Field(min_length=1)
    scope: Literal["lexical", "semantic", "pragmatic", "task", "external_action"]
    status: Literal["approved", "needs-evidence", "rejected", "hold"]
    reviewer: str = Field(min_length=1)
    decided_at: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    patch: PatchModel | None = None


def _record(number: int) -> dict[str, Any]:
    return {
        "record_id": f"REC-{number:06d}",
        "input_sha256": f"{number:064x}",
        "lemma": f"候補{number}",
        "meaning_candidates": [],
        "approval": {"review_scopes": list(REVIEW_SCOPES)},
    }


def _decision_payload(record_id: str) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "decisions": [
            {
                "scope": "semantic",
                "status": "approved",
                "rationale": "意味候補と根拠を確認した。",
                "patch": {"polarity": "neutral", "intensity": 0.0},
            },
            {
                "scope": "pragmatic",
                "status": "needs-evidence",
                "rationale": "語用条件の根拠が不足している。",
                "patch": {},
            },
            {
                "scope": "task",
                "status": "approved",
                "rationale": "Task候補なしとして確認した。",
                "patch": {"task_candidates": []},
            },
            {
                "scope": "external_action",
                "status": "approved",
                "rationale": "外部Action Riskなしとして確認した。",
                "patch": {"external_action_risk": False},
            },
        ],
    }


class MockProvider:
    def __init__(self, *, failures_before_success: int = 0) -> None:
        self.calls = 0
        self.failures_before_success = failures_before_success

    def review_batch(self, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self.calls += 1
        if self.calls <= self.failures_before_success:
            raise OSError("transient mock provider failure")
        return [
            {
                "custom_id": request["custom_id"],
                **_decision_payload(request["custom_id"]),
            }
            for request in requests
        ]


def test_125000_records_are_split_within_batch_request_limit() -> None:
    records = [_record(number) for number in range(125_000)]
    chunks = split_records(records)
    assert [len(chunk) for chunk in chunks] == [50_000, 50_000, 25_000]
    assert all(len(chunk) <= MAX_BATCH_REQUESTS for chunk in chunks)


def test_custom_id_matches_record_id_in_prepared_requests(tmp_path: Path) -> None:
    records = [_record(number) for number in range(3)]
    manifest = prepare_bulk_review_job(records, tmp_path, max_batch_requests=2)
    assert manifest["provider_batch_count"] == 2
    rows = []
    for batch in manifest["provider_batches"]:
        rows.extend(
            json.loads(line)
            for line in (tmp_path / batch["path"]).read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    assert [row["custom_id"] for row in rows] == [
        record["record_id"] for record in records
    ]
    for record, row in zip(records, rows, strict=True):
        assert build_batch_request(record)["custom_id"] == record["record_id"]
        assert row["body"]["text"]["format"]["type"] == "json_schema"
        assert row["body"]["text"]["format"]["strict"] is True


def test_mock_provider_merges_without_missing_or_duplicate_records(tmp_path: Path) -> None:
    records = [_record(number) for number in range(13)]
    summary = execute_with_provider(
        records,
        tmp_path,
        MockProvider(),
        max_batch_requests=5,
        decided_at="2026-08-09T03:18:00+09:00",
    )
    assert summary["total_records"] == 13
    assert summary["success_records"] == 13
    assert summary["error_records"] == 0
    assert summary["decision_count"] == 13 * 4
    ledger = [
        json.loads(line)
        for line in (tmp_path / "bulk-review/decision_ledger.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert len({(item["record_id"], item["scope"]) for item in ledger}) == 13 * 4
    assert {item["record_id"] for item in ledger} == {
        record["record_id"] for record in records
    }


def test_decision_ledger_matches_existing_schema_contract(tmp_path: Path) -> None:
    records = [_record(1), _record(2)]
    execute_with_provider(
        records,
        tmp_path,
        MockProvider(),
        decided_at="2026-08-09T03:18:00+09:00",
    )
    schema = json.loads(
        (ROOT / "schemas/semantic_decision_ledger.schema.json").read_text(
            encoding="utf-8"
        )
    )
    allowed_properties = set(schema["properties"])
    required_properties = set(schema["required"])
    patch_properties = set(schema["properties"]["patch"]["properties"])
    ledger = [
        json.loads(line)
        for line in (tmp_path / "bulk-review/decision_ledger.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    for item in ledger:
        LedgerModel.model_validate(item)
        assert required_properties <= set(item)
        assert set(item) <= allowed_properties
        assert item["scope"] in schema["properties"]["scope"]["enum"]
        assert item["status"] in schema["properties"]["status"]["enum"]
        assert set(item.get("patch", {})) <= patch_properties


def test_merge_rejects_missing_and_duplicate_results(tmp_path: Path) -> None:
    records = [_record(1), _record(2)]
    one = {
        "custom_id": records[0]["record_id"],
        **_decision_payload(records[0]["record_id"]),
    }
    with pytest.raises(ValueError, match="missing review results"):
        merge_batch_results(records, [one], tmp_path)
    with pytest.raises(ValueError, match="duplicate result custom_id"):
        merge_batch_results(records[:1], [one, one], tmp_path)


def test_retry_stops_after_transient_failures_and_succeeds(tmp_path: Path) -> None:
    provider = MockProvider(failures_before_success=2)
    summary = execute_with_provider(
        [_record(1)],
        tmp_path,
        provider,
        retry_attempts=3,
        decided_at="2026-08-09T03:18:00+09:00",
    )
    assert provider.calls == 3
    assert summary["success_records"] == 1
