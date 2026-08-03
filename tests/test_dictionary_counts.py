import json
from pathlib import Path

import yaml

from deterministic_japanese_parser_mcp import ParserEngine

ROOT = Path(__file__).resolve().parents[1]


def _metaphor_documents() -> list[tuple[Path, dict]]:
    return [
        (path, json.loads(path.read_text(encoding="utf-8")))
        for path in sorted((ROOT / "dictionaries/system/metaphors").glob("*.json"))
        if path.name not in {"manifest.json", "overrides.json"}
    ]


def _rule_documents() -> list[dict]:
    return [
        yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for path in sorted((ROOT / "dictionaries/system/rules").glob("*.yaml"))
    ]


def _effective_gold_count() -> int:
    by_id: dict[str, dict] = {}
    for path in sorted((ROOT / "tests/gold").glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for case in doc.get("cases", []):
            by_id[case["id"]] = case
    return len(by_id)


def test_expanded_dictionary_volume_is_exact():
    engine = ParserEngine()
    rules = sum(
        len(items)
        for doc in _rule_documents()
        for items in doc.get("intents", {}).values()
    )
    workflows = [
        item
        for item in engine.bundle.templates["templates"]
        if item.get("intent") == "workflow"
    ]

    assert len(engine.bundle.metaphors["entries"]) == 452
    assert rules == 339
    assert _effective_gold_count() == 649
    assert len(engine.bundle.synonyms["groups"]) == 100
    assert len(engine.bundle.templates["templates"]) == 63
    assert len(workflows) == 42


def test_metaphor_manifest_matches_every_category_file():
    manifest = json.loads(
        (ROOT / "dictionaries/system/metaphors/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    actual = {
        path.name: len(doc.get("entries", []))
        for path, doc in _metaphor_documents()
    }
    engine = ParserEngine()

    assert manifest["dictionary_version"] == "1.2.0"
    assert manifest["metaphor_entries"] == len(
        engine.bundle.metaphors["entries"]
    )
    assert manifest["category_files"] == actual
    assert sum(actual.values()) == 452


def test_all_twenty_one_intents_received_common_usage_expansion():
    first_wave = yaml.safe_load(
        (
            ROOT
            / "dictionaries/system/rules/common_usage_expansion.yaml"
        ).read_text(encoding="utf-8")
    )["intents"]
    second_wave = yaml.safe_load(
        (
            ROOT
            / "dictionaries/system/rules/extended_usage_2026_08.yaml"
        ).read_text(encoding="utf-8")
    )["intents"]

    assert len(first_wave) == 21
    assert all(len(items) == 3 for items in first_wave.values())
    assert sum(len(items) for items in first_wave.values()) == 63
    assert len(second_wave) == 21
    assert all(len(items) == 6 for items in second_wave.values())
    assert sum(len(items) for items in second_wave.values()) == 126


def test_new_workflow_ids_are_present_and_ordered():
    engine = ParserEngine()
    workflows = {
        item["id"]: item
        for item in engine.bundle.templates["templates"]
        if item.get("intent") == "workflow"
    }
    expected = {
        "WF-REQUIREMENT_ANALYSIS",
        "WF-BUG_REPRODUCTION",
        "WF-ROOT_CAUSE_ANALYSIS",
        "WF-DOCUMENT_REVISION",
        "WF-DATA-MIGRATION",
        "WF-DEPENDENCY-UPGRADE",
        "WF-ACCOUNT-AUTH-CHANGE",
        "WF-UI-ACCESSIBILITY-REVIEW",
        "WF-KNOWLEDGE-BASE-UPDATE",
        "WF-ROLLBACK-RECOVERY",
        "WF-DIALOGUE-REPAIR",
        "WF-AMBIGUITY-RESOLUTION",
        "WF-SCOPE-FREEZE",
        "WF-RISK-REVIEW",
        "WF-EXTERNAL-ACTION-SAFETY",
        "WF-PRIVACY-REVIEW",
        "WF-SECRET-ROTATION",
        "WF-ACCESS-REVIEW",
        "WF-INCIDENT-COMMUNICATION",
        "WF-OBSERVABILITY-SETUP",
        "WF-DATA-CONTRACT-CHANGE",
        "WF-SCHEMA-MIGRATION-SAFE",
        "WF-WEBHOOK-INTEGRATION",
        "WF-API-DEPRECATION",
        "WF-MOBILE-RELEASE",
        "WF-RESPONSIVE-UI-REVIEW",
        "WF-ACCESSIBILITY-REMEDIATION",
        "WF-CUSTOMER-ONBOARDING",
        "WF-SUPPORT-DEFLECTION",
        "WF-PRICING-CHANGE",
        "WF-PAYMENT-FLOW-CHANGE",
        "WF-CONTENT-PUBLICATION",
        "WF-LOCALIZATION-REVIEW",
        "WF-REPOSITORY-PUBLICATION",
    }
    assert expected <= set(workflows)
    for workflow_id in expected:
        orders = [step["order"] for step in workflows[workflow_id]["steps"]]
        assert orders == list(range(1, len(orders) + 1))
