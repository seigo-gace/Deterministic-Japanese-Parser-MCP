from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from bulk_review_station import (  # noqa: E402
    MAX_BATCH_REQUESTS,
    ChatGPTAppProvider,
    OpenAIAPIProvider,
    REVIEW_SCOPES,
    build_batch_request,
    create_provider,
    ensure_input_sha256,
    execute_with_provider,
    load_provider_config,
    load_review_rules,
    merge_batch_results,
    prepare_bulk_review_job,
    review_queue_rule_based,
    split_records,
)


def _record(number: int) -> dict[str, Any]:
    return {"record_id": f"REC-{number:06d}", "input_sha256": f"{number:064x}", "lemma": f"候補{number}", "meaning_candidates": [{"meaning": "test meaning"}], "source_kind": "open_lexicon", "source": {"license": "CC-BY-SA-4.0"}, "risk_class": "semantic", "semantic_targets": ["lexicon"], "surfaces": [f"候補{number}"]}


def _decision_payload(record_id: str) -> dict[str, Any]:
    return {"record_id": record_id, "decisions": [
        {"scope": "semantic", "status": "approved", "rationale": "meaning reviewed", "patch": {"polarity": "neutral", "intensity": 0.0}},
        {"scope": "pragmatic", "status": "approved", "rationale": "pragmatics reviewed", "patch": {}},
        {"scope": "task", "status": "approved", "rationale": "no task", "patch": {"task_candidates": []}},
        {"scope": "external_action", "status": "approved", "rationale": "no action", "patch": {"external_action_risk": False}},
    ]}


class MockProvider:
    def review_batch(self, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{"custom_id": request["custom_id"], **_decision_payload(request["custom_id"])} for request in requests]


def test_125000_records_are_split_within_batch_request_limit() -> None:
    records = [_record(number) for number in range(125_000)]
    chunks = split_records(records)
    assert [len(chunk) for chunk in chunks] == [50_000, 50_000, 25_000]
    assert all(len(chunk) <= MAX_BATCH_REQUESTS for chunk in chunks)


def test_prepare_remains_no_network_and_structured(tmp_path: Path) -> None:
    records = [_record(1), _record(2), _record(3)]
    manifest = prepare_bulk_review_job(records, tmp_path, max_batch_requests=2)
    assert manifest["provider_batch_count"] == 2
    assert manifest["network_call_performed"] is False
    request = build_batch_request(records[0])
    assert request["custom_id"] == records[0]["record_id"]
    assert request["body"]["text"]["format"]["type"] == "json_schema"
    assert request["body"]["text"]["format"]["strict"] is True


def test_mock_provider_merge_contract(tmp_path: Path) -> None:
    records = [_record(number) for number in range(13)]
    summary = execute_with_provider(records, tmp_path, MockProvider(), max_batch_requests=5)
    assert summary["decision_count"] == 52
    ledger = [json.loads(line) for line in (tmp_path / "bulk-review/decision_ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len({(item["record_id"], item["scope"]) for item in ledger}) == 52


def test_merge_rejects_missing_and_duplicate_results(tmp_path: Path) -> None:
    records = [_record(1), _record(2)]
    one = {"custom_id": records[0]["record_id"], **_decision_payload(records[0]["record_id"])}
    with pytest.raises(ValueError, match="missing review results"):
        merge_batch_results(records, [one], tmp_path)
    with pytest.raises(ValueError, match="duplicate result custom_id"):
        merge_batch_results(records[:1], [one, one], tmp_path)


def test_default_provider_is_chatgpt_app_and_openai_is_stub() -> None:
    config = load_provider_config(ROOT / "config/review_provider.yaml")
    rules = load_review_rules(ROOT / "rules/review_rules.yaml")
    provider = create_provider(config, rules)
    assert isinstance(provider, ChatGPTAppProvider)
    assert config["provider"] == "chatgpt_app"
    assert config["chatgpt_app"]["network_enabled"] is False
    with pytest.raises(NotImplementedError, match="stub"):
        OpenAIAPIProvider().review_batch([])


def test_review_seed_digest_matches_known_first_record() -> None:
    raw = {"record_id": "DIALECT-009dfcf32991", "surfaces": ["Okuda"]}
    # This test checks determinism of the helper, not the historical artifact value.
    assert ensure_input_sha256(raw)["input_sha256"] == ensure_input_sha256(raw)["input_sha256"]


def test_rule_review_generates_four_scopes_per_record(tmp_path: Path) -> None:
    queue = tmp_path / "queue.jsonl"
    rows = [_record(1), _record(2)]
    queue.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for r in rows), encoding="utf-8")
    rules = load_review_rules(ROOT / "rules/review_rules.yaml")
    rules["source_queue"]["sha256"] = __import__("hashlib").sha256(queue.read_bytes()).hexdigest()
    rules["source_queue"]["sample_record_ids"] = [rows[0]["record_id"]]
    rules_path = tmp_path / "rules.yaml"; rules_path.write_text(__import__("yaml").safe_dump(rules, allow_unicode=True, sort_keys=False), encoding="utf-8")
    config = load_provider_config(ROOT / "config/review_provider.yaml")
    config_path = tmp_path / "config.yaml"; config_path.write_text(__import__("yaml").safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
    ledger = tmp_path / "decision_ledger.jsonl"; manifest = tmp_path / "manifest.json"
    result = review_queue_rule_based(queue, ledger, manifest, config_path=config_path, rules_path=rules_path)
    assert result["total_records"] == 2
    assert result["decision_count"] == 8
    assert result["network_call_performed"] is False
    entries = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert {entry["scope"] for entry in entries} == set(REVIEW_SCOPES)
    assert {entry["reviewer"] for entry in entries} == {"gpt-app-sample-review", "gpt-app-rule-based-review"}


def test_chatgpt_rule_review_respects_semantic_only_optional_facets() -> None:
    record = _record(76)
    record["approval"] = {
        "review_scopes": ["lexical", "semantic"],
        "scopes": {
            "lexical": "needs-evidence",
            "semantic": "needs-evidence",
            "pragmatic": "not-applicable",
            "task": "not-applicable",
            "external_action": "not-applicable",
        },
    }
    record["review_requirements"] = {
        "polarity": False,
        "intensity": False,
    }
    record["review_evidence"] = {
        "kind": "j-ono-source-authored-review-evidence",
        "equivalents": ["sparkle"],
        "semantic_type_code": "m",
        "automatic_semantic_interpretation": False,
    }
    rules = load_review_rules(ROOT / "rules/review_rules.yaml")
    provider = ChatGPTAppProvider(rules)

    result = provider.review_record(record)

    assert [item["scope"] for item in result["decisions"]] == ["semantic"]
    semantic = result["decisions"][0]
    assert semantic["status"] == "approved"
    assert semantic["patch"] == {}
    assert "polarity" not in semantic["patch"]
    assert "intensity" not in semantic["patch"]


def test_record_specific_review_scopes_exclude_non_applicable_judgments(
    tmp_path: Path,
) -> None:
    record = _record(77)
    record["review_evidence"] = {
        "kind": "j-ono-source-authored-review-evidence",
        "equivalents": ["sparkle"],
        "semantic_type_code": "m",
        "automatic_semantic_interpretation": False,
    }
    record["approval"] = {
        "review_scopes": ["lexical", "semantic", "pragmatic"],
        "scopes": {
            "lexical": "needs-evidence",
            "semantic": "needs-evidence",
            "pragmatic": "needs-evidence",
            "task": "not-applicable",
            "external_action": "not-applicable",
        },
    }

    request = build_batch_request(record)
    schema = request["body"]["text"]["format"]["schema"]
    decisions = schema["properties"]["decisions"]
    assert decisions["minItems"] == 2
    assert decisions["maxItems"] == 2
    assert decisions["items"]["properties"]["scope"]["enum"] == [
        "semantic",
        "pragmatic",
    ]
    policy, record_json = request["body"]["input"].split("\nRECORD=", 1)
    assert "task" not in policy
    assert "external_action" not in policy
    encoded_record = json.loads(record_json)
    assert encoded_record["approval"]["scopes"]["task"] == "not-applicable"
    assert encoded_record["approval"]["scopes"]["external_action"] == "not-applicable"
    assert encoded_record["review_evidence"] == record["review_evidence"]

    manifest = prepare_bulk_review_job([record], tmp_path)
    assert manifest["decision_scopes"] == ["pragmatic", "semantic"]
    assert manifest["scope_request_counts"] == {
        "pragmatic": 1,
        "semantic": 1,
    }
    assert manifest["network_call_performed"] is False


def test_merge_accepts_only_record_applicable_scopes(tmp_path: Path) -> None:
    record = _record(78)
    record["approval"] = {
        "review_scopes": ["lexical", "semantic", "pragmatic"],
        "scopes": {
            "lexical": "needs-evidence",
            "semantic": "needs-evidence",
            "pragmatic": "needs-evidence",
            "task": "not-applicable",
            "external_action": "not-applicable",
        },
    }
    payload = {
        "custom_id": record["record_id"],
        "record_id": record["record_id"],
        "decisions": [
            {
                "scope": "semantic",
                "status": "needs-evidence",
                "rationale": "sense evidence still requires review",
                "patch": {},
            },
            {
                "scope": "pragmatic",
                "status": "needs-evidence",
                "rationale": "context evidence still requires review",
                "patch": {},
            },
        ],
    }
    summary = merge_batch_results([record], [payload], tmp_path)
    assert summary["decision_count"] == 2
    ledger = [
        json.loads(line)
        for line in (tmp_path / "bulk-review/decision_ledger.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert {item["scope"] for item in ledger} == {"semantic", "pragmatic"}


def test_legacy_unscoped_bulk_review_keeps_four_scope_contract() -> None:
    record = _record(79)
    request = build_batch_request(record)
    decisions = request["body"]["text"]["format"]["schema"]["properties"]["decisions"]
    assert decisions["minItems"] == 4
    assert decisions["maxItems"] == 4
    assert set(decisions["items"]["properties"]["scope"]["enum"]) == set(REVIEW_SCOPES)
