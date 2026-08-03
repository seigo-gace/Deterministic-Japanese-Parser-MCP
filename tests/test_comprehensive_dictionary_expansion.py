from __future__ import annotations

import json
from pathlib import Path

import yaml

from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine
from deterministic_japanese_parser_mcp.normalizer import normalize_with_map

ROOT = Path(__file__).resolve().parents[1]
NEW_METAPHOR_FILES = {
    "17_dialogue_repair_alignment.json",
    "18_temporal_status_progress.json",
    "19_negation_constraint_exclusion.json",
    "20_emotion_attitude_feedback.json",
    "21_planning_decision_risk.json",
    "22_incident_debug_recovery.json",
    "23_document_explanation_revision.json",
    "24_collaboration_ownership_escalation.json",
    "25_data_api_integration.json",
    "26_security_privacy_governance.json",
    "27_ui_ux_accessibility.json",
    "28_sales_support_customer.json",
    "29_daily_casual_speech.json",
    "30_pragmatics_indirectness.json",
}
NEW_RULE_FILE = "extended_usage_2026_08.yaml"
NEW_SYNONYM_FILE = "comprehensive_groups_2026_08.yaml"
NEW_WORKFLOW_FILE = "comprehensive_workflows_2026_08.yaml"


def _load_cases(filename: str) -> list[dict]:
    return json.loads(
        (ROOT / "tests/gold" / filename).read_text(encoding="utf-8")
    )["cases"]


def _request(case: dict) -> AnalyzeRequest:
    request = dict(case.get("request", {}))
    request.setdefault("original_text", case["text"])
    request.setdefault("deadline_ms", 50)
    return AnalyzeRequest(**request)


def test_comprehensive_dictionary_totals_are_fixed():
    engine = ParserEngine()
    gold_count = sum(
        len(json.loads(path.read_text(encoding="utf-8")).get("cases", []))
        for path in sorted((ROOT / "tests/gold").glob("*.json"))
    )
    workflow_count = sum(
        1
        for item in engine.bundle.templates["templates"]
        if item.get("intent") == "workflow"
    )
    assert len(engine.bundle.metaphors["entries"]) == 452
    assert len(engine.rules.compiled) == 339
    assert len(engine.bundle.synonyms["groups"]) == 100
    assert len(engine.bundle.templates["templates"]) == 63
    assert workflow_count == 42
    assert gold_count == 649


def test_every_second_wave_metaphor_has_gold_and_is_detected():
    entries: dict[str, dict] = {}
    for filename in sorted(NEW_METAPHOR_FILES):
        doc = json.loads(
            (ROOT / "dictionaries/system/metaphors" / filename).read_text(
                encoding="utf-8"
            )
        )
        assert len(doc["entries"]) == 18
        for item in doc["entries"]:
            assert item["expression"] not in entries
            entries[item["expression"]] = item
    assert len(entries) == 252

    cases = [
        case
        for path in sorted((ROOT / "tests/gold").glob("cases-11-*.json"))
        for case in json.loads(path.read_text(encoding="utf-8"))["cases"]
    ]
    assert len(cases) == 252
    expected_expressions = {
        expression
        for case in cases
        for expression in case["expected"].get("metaphors", [])
    }
    assert set(entries) == expected_expressions

    engine = ParserEngine()
    detected: set[str] = set()
    for case in cases:
        response = engine.analyze(_request(case))
        actual = {item.expression for item in response.metaphors}
        expected = set(case["expected"]["metaphors"])
        assert expected <= actual, {
            "case": case["id"],
            "expected": sorted(expected),
            "actual": sorted(actual),
        }
        detected.update(actual.intersection(entries))
    assert detected == set(entries)


def test_every_second_wave_rule_is_indexed_matches_gold_and_preserves_meaning():
    expansion = yaml.safe_load(
        (ROOT / "dictionaries/system/rules" / NEW_RULE_FILE).read_text(
            encoding="utf-8"
        )
    )
    flattened = [
        (intent_type, item)
        for intent_type, items in expansion["intents"].items()
        for item in items
    ]
    assert len(flattened) == 126
    assert len(expansion["intents"]) == 21
    assert all(len(items) == 6 for items in expansion["intents"].values())

    cases = _load_cases("cases-12.json")
    assert len(cases) == 126

    engine = ParserEngine()
    compiled_by_id = {
        item["id"]: (index, intent_type, pattern)
        for index, (intent_type, item, pattern) in enumerate(engine.rules.compiled)
        if item["id"].startswith("EXT-")
    }
    expected_rule_ids = {item["id"] for _, item in flattened}
    assert set(compiled_by_id) == expected_rule_ids
    assert all(
        index not in engine.rules.always_scan
        for index, _, _ in compiled_by_id.values()
    )

    seen_intents: set[str] = set()
    for (intent_type, item), case in zip(flattened, cases, strict=True):
        normalized, _ = normalize_with_map(case["text"])
        index, compiled_intent, pattern = compiled_by_id[item["id"]]
        assert compiled_intent == intent_type
        assert index in engine.rules.candidate_indices(normalized), item["id"]
        assert pattern.search(normalized, timeout=engine.rules.timeout), item["id"]

        response = engine.analyze(_request(case))
        final_types = {intent.type for intent in response.intents}
        assert intent_type in final_types, {
            "case": case["id"],
            "rule_id": item["id"],
            "rule_intent": intent_type,
            "final_intents": sorted(final_types),
        }
        if intent_type in {"prohibition", "out_of_scope"}:
            assert response.execution_allowed is False
        seen_intents.update(final_types)

    assert set(expansion["intents"]) <= seen_intents


def test_second_wave_synonym_groups_are_loaded_and_queryable():
    fragment = yaml.safe_load(
        (
            ROOT
            / "dictionaries/system/synonyms.d"
            / NEW_SYNONYM_FILE
        ).read_text(encoding="utf-8")
    )
    expected = set(fragment["groups"])
    assert len(expected) == 60

    engine = ParserEngine()
    assert expected <= set(engine.bundle.synonyms["groups"])
    for canonical in expected:
        assert canonical in engine.canonicalizer.ids(canonical)


def test_second_wave_workflows_are_loaded_with_ordered_steps():
    fragment = yaml.safe_load(
        (
            ROOT
            / "dictionaries/system/task_templates.d"
            / NEW_WORKFLOW_FILE
        ).read_text(encoding="utf-8")
    )
    expected_ids = {item["id"] for item in fragment["templates"]}
    assert len(expected_ids) == 24

    engine = ParserEngine()
    loaded = {
        item["id"]: item
        for item in engine.bundle.templates["templates"]
        if item["id"] in expected_ids
    }
    assert set(loaded) == expected_ids
    for item in loaded.values():
        steps = item["steps"]
        assert len(steps) == 7
        assert [step["order"] for step in steps] == list(range(1, 8))
        assert all(step["action"] for step in steps)
