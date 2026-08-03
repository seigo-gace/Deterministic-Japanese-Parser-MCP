from __future__ import annotations

import json
from pathlib import Path

import yaml

from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine
from deterministic_japanese_parser_mcp.normalizer import normalize_with_map

ROOT = Path(__file__).resolve().parents[1]
NEW_METAPHOR_FILES = {
    "13_everyday_instruction.json",
    "14_business_communication.json",
    "15_development_operations.json",
    "16_document_analysis.json",
}


def _load_cases(filename: str) -> list[dict]:
    return json.loads(
        (ROOT / "tests/gold" / filename).read_text(encoding="utf-8")
    )["cases"]


def _request(case: dict) -> AnalyzeRequest:
    request = dict(case.get("request", {}))
    request.setdefault("original_text", case["text"])
    request.setdefault("deadline_ms", 50)
    return AnalyzeRequest(**request)


def test_every_new_metaphor_has_a_gold_case_and_is_detected():
    entries: dict[str, dict] = {}
    for filename in sorted(NEW_METAPHOR_FILES):
        doc = json.loads(
            (ROOT / "dictionaries/system/metaphors" / filename).read_text(
                encoding="utf-8"
            )
        )
        for item in doc["entries"]:
            entries[item["expression"]] = item

    cases = _load_cases("cases-09.json")
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


def test_every_common_usage_rule_is_indexed_matches_gold_and_preserves_meaning():
    expansion = yaml.safe_load(
        (
            ROOT
            / "dictionaries/system/rules/common_usage_expansion.yaml"
        ).read_text(encoding="utf-8")
    )
    expected_rule_ids = {
        item["id"]
        for items in expansion["intents"].values()
        for item in items
    }
    assert len(expected_rule_ids) == 63

    engine = ParserEngine()
    compiled_by_id = {
        item["id"]: (index, intent_type, pattern)
        for index, (intent_type, item, pattern) in enumerate(engine.rules.compiled)
        if item["id"] in expected_rule_ids
    }
    assert set(compiled_by_id) == expected_rule_ids
    assert all(
        index not in engine.rules.always_scan
        for index, _, _ in compiled_by_id.values()
    )

    candidate_rule_ids: set[str] = set()
    regex_matched_rule_ids: set[str] = set()
    final_intents_seen: set[str] = set()

    for case in _load_cases("cases-10.json"):
        normalized, _ = normalize_with_map(case["text"])
        candidate_indices = engine.rules.candidate_indices(normalized)
        response = engine.analyze(_request(case))
        final_types = {item.type for item in response.intents}
        expected_types = set(case["expected"].get("intents", []))
        assert expected_types <= final_types, {
            "case": case["id"],
            "expected": sorted(expected_types),
            "actual": sorted(final_types),
        }
        final_intents_seen.update(final_types)

        for rule_id, (index, intent_type, pattern) in compiled_by_id.items():
            if index not in candidate_indices:
                continue
            candidate_rule_ids.add(rule_id)
            if pattern.search(normalized, timeout=engine.rules.timeout):
                regex_matched_rule_ids.add(rule_id)
                assert intent_type in final_types, {
                    "case": case["id"],
                    "rule_id": rule_id,
                    "rule_intent": intent_type,
                    "final_intents": sorted(final_types),
                }

    assert candidate_rule_ids == expected_rule_ids, {
        "not_indexed_by_any_gold": sorted(expected_rule_ids - candidate_rule_ids),
    }
    assert regex_matched_rule_ids == expected_rule_ids, {
        "not_matched_by_any_gold": sorted(
            expected_rule_ids - regex_matched_rule_ids
        ),
    }
    assert set(expansion["intents"]) <= final_intents_seen


def test_all_new_synonym_groups_are_queryable_without_hiding_overlap():
    doc = yaml.safe_load(
        (ROOT / "dictionaries/system/synonyms.yaml").read_text(encoding="utf-8")
    )
    engine = ParserEngine()
    new_groups = {
        "依頼",
        "承認",
        "合意",
        "担当",
        "移管",
        "保留解除",
        "再現",
        "原因特定",
        "影響確認",
        "暫定対応",
        "恒久対応",
        "凍結",
        "解除",
        "要約",
        "具体化",
        "抽象化",
        "説明",
        "整合",
        "分割",
        "一括処理",
    }
    assert new_groups <= set(doc["groups"])
    for canonical in new_groups:
        assert canonical in engine.canonicalizer.ids(canonical)

    overlap = engine.canonicalizer.ids("切り分け")
    assert "調査" in overlap
    assert "分解" in overlap
    assert "原因特定" in overlap
