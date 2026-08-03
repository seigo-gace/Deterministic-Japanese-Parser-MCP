from __future__ import annotations

import json
from pathlib import Path

import yaml

from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine

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


def test_every_common_usage_rule_has_a_gold_case_and_fires():
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
    fired: set[str] = set()
    for case in _load_cases("cases-10.json"):
        response = engine.analyze(_request(case))
        fired.update(
            item.rule_id
            for item in response.intents
            if item.rule_id in expected_rule_ids
        )
    assert fired == expected_rule_ids, {
        "missing_rule_ids": sorted(expected_rule_ids - fired),
        "fired_count": len(fired),
    }


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
