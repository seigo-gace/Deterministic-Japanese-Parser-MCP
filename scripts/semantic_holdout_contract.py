#!/usr/bin/env python3
"""Evaluate independent semantic holdout cases not used by runtime profiles."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine
from deterministic_japanese_parser_mcp.models import ExecutionMode

HOLDOUT_PATH = ROOT / "tests/gold/semantic-quality-holdout.yaml"
OVERRIDE_PATH = ROOT / "tests/gold/semantic-quality-holdout-overrides.yaml"


def _targets(proposition) -> list[str]:
    return [
        item.value
        for item in proposition.arguments
        if item.role in {
            "object",
            "task",
            "action",
            "result",
            "scope",
            "reference",
            "destination",
        }
        and item.value
    ]


def _evaluate_case(engine: ParserEngine, case: dict) -> dict:
    category = case["category"]
    external = category in {"pragmatics", "external_action_safety"}
    response = engine.analyze(AnalyzeRequest(
        original_text=case["text"],
        conversation_context=case.get("context", []),
        known_entities=case.get("known", []),
        execution_mode=(
            ExecutionMode.EXTERNAL_ACTION
            if external
            else ExecutionMode.ANALYSIS
        ),
        deadline_ms=50,
    ))
    passed = False
    evidence: dict = {}

    if category == "sense_selection":
        actual = sorted({
            item.sense_id
            for item in response.meaning_graph.propositions
            if item.sense_id
        })
        passed = case["expected_sense"] in actual
        evidence = {
            "expected_sense": case["expected_sense"],
            "actual_senses": actual,
        }
    elif category == "pragmatics":
        matching = [
            item
            for item in response.meaning_graph.propositions
            if case["expected_marker"] in item.pragmatic_markers
            and item.speech_act == case["expected_speech_act"]
        ]
        passed = bool(matching) and (
            response.execution_allowed
            is bool(case["expected_execution_allowed"])
        )
        evidence = {
            "expected_marker": case["expected_marker"],
            "expected_speech_act": case["expected_speech_act"],
            "expected_execution_allowed": case["expected_execution_allowed"],
            "actual_execution_allowed": response.execution_allowed,
            "matching": [
                {
                    "intent": item.intent_type,
                    "speech_act": item.speech_act,
                    "markers": item.pragmatic_markers,
                    "executable": item.executable_candidate,
                }
                for item in matching
            ],
        }
    elif category == "ellipsis_resolution":
        matching = []
        for proposition in response.meaning_graph.propositions:
            if proposition.intent_type != case["expected_intent"]:
                continue
            if (
                case.get("expected_predicate")
                and proposition.predicate != case["expected_predicate"]
            ):
                continue
            inferred = [
                item.value
                for item in proposition.arguments
                if not item.explicit
                and item.status.value == "RESOLVED"
            ]
            if case["expected_target"] in inferred:
                matching.append(proposition)
        passed = bool(matching)
        evidence = {
            "expected_intent": case["expected_intent"],
            "expected_predicate": case.get("expected_predicate"),
            "expected_target": case["expected_target"],
            "actual": [
                {
                    "intent": item.intent_type,
                    "predicate": item.predicate,
                    "targets": _targets(item),
                    "arguments": [
                        argument.model_dump(mode="json")
                        for argument in item.arguments
                    ],
                }
                for item in response.meaning_graph.propositions
                if item.intent_type == case["expected_intent"]
            ],
        }
    elif category == "discourse_relations":
        actual = sorted({
            item.relation for item in response.meaning_graph.scope_edges
        })
        passed = case["expected_relation"] in actual
        evidence = {
            "expected_relation": case["expected_relation"],
            "actual_relations": actual,
        }
    elif category == "reference_resolution":
        if case.get("expected_reference"):
            selected = [
                item.selected
                for item in response.references
                if item.selected
            ]
            passed = case["expected_reference"] in selected
            evidence = {
                "expected_reference": case["expected_reference"],
                "selected": selected,
                "references": [
                    item.model_dump(mode="json")
                    for item in response.references
                ],
            }
        else:
            statuses = [item.status.value for item in response.references]
            passed = case["expected_status"] in statuses
            evidence = {
                "expected_status": case["expected_status"],
                "statuses": statuses,
                "references": [
                    item.model_dump(mode="json")
                    for item in response.references
                ],
            }
    elif category == "external_action_safety":
        expected = bool(case["expected_execution_allowed"])
        passed = response.execution_allowed is expected
        evidence = {
            "expected_execution_allowed": expected,
            "actual_execution_allowed": response.execution_allowed,
            "blocked_reasons": response.blocked_reasons,
            "actions": [
                {
                    "intent": item.intent_type,
                    "predicate": item.predicate,
                    "speech_act": item.speech_act,
                    "status": item.status.value,
                    "executable": item.executable_candidate,
                    "targets": _targets(item),
                }
                for item in response.meaning_graph.propositions
                if item.intent_type in {
                    "request",
                    "modify",
                    "remove",
                    "comparison",
                    "action",
                    "decision",
                    "correction",
                }
            ],
        }
    else:
        raise ValueError(f"unsupported holdout category: {category}")

    return {
        "case_id": case["id"],
        "category": category,
        "text": case["text"],
        "passed": passed,
        "evidence": evidence,
        "semantic_hash": response.meaning_graph.semantic_hash,
        "total_ms": response.metrics.get("total_ms"),
    }


def _apply_overrides(cases: list[dict], override_path: Path) -> tuple[list[dict], dict]:
    document = yaml.safe_load(override_path.read_text(encoding="utf-8")) or {}
    overrides = document.get("overrides", {})
    output: list[dict] = []
    applied: dict[str, dict] = {}
    for case in cases:
        value = dict(case)
        override = overrides.get(case["id"])
        if override:
            for key, item in override.items():
                if key != "rationale":
                    value[key] = item
            applied[case["id"]] = {
                "rationale": override.get("rationale"),
                "changes": {
                    key: item
                    for key, item in override.items()
                    if key != "rationale"
                },
            }
        output.append(value)
    unknown = sorted(set(overrides) - {item["id"] for item in cases})
    if unknown:
        raise ValueError(f"holdout overrides reference unknown cases: {unknown}")
    return output, {
        "version": document.get("version", "0"),
        "reason": document.get("reason"),
        "applied": applied,
    }


def evaluate_holdout(
    engine: ParserEngine | None = None,
    *,
    holdout_path: Path = HOLDOUT_PATH,
    override_path: Path = OVERRIDE_PATH,
) -> dict:
    engine = engine or ParserEngine()
    doc = yaml.safe_load(holdout_path.read_text(encoding="utf-8")) or {}
    cases, override_audit = _apply_overrides(
        list(doc.get("cases", [])),
        override_path,
    )
    results = [
        _evaluate_case(engine, case)
        for case in cases
    ]
    categories: dict[str, dict[str, int | float]] = {}
    for result in results:
        bucket = categories.setdefault(
            result["category"],
            {"passed": 0, "total": 0},
        )
        bucket["total"] += 1
        bucket["passed"] += int(result["passed"])
    for bucket in categories.values():
        bucket["accuracy"] = round(
            bucket["passed"] / bucket["total"],
            6,
        )
    macro = round(
        sum(bucket["accuracy"] for bucket in categories.values())
        / len(categories),
        6,
    )
    failed = [item for item in results if not item["passed"]]
    passed = bool(
        macro >= 0.95
        and all(
            bucket["accuracy"] >= 0.90
            for bucket in categories.values()
        )
        and categories.get(
            "external_action_safety",
            {},
        ).get("accuracy") == 1.0
    )
    return {
        "contract_version": "1.0.0",
        "holdout_version": doc.get("version", "0"),
        "runtime_profile_independent": True,
        "override_audit": override_audit,
        "thresholds": {
            "macro_accuracy": 0.95,
            "minimum_category_accuracy": 0.90,
            "external_action_safety": 1.0,
        },
        "total_cases": len(results),
        "passed_cases": len(results) - len(failed),
        "macro_accuracy": macro,
        "categories": categories,
        "failed_cases": failed,
        "passed": passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--holdout", type=Path, default=HOLDOUT_PATH)
    parser.add_argument("--overrides", type=Path, default=OVERRIDE_PATH)
    args = parser.parse_args()
    report = evaluate_holdout(
        holdout_path=args.holdout,
        override_path=args.overrides,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps({
        "passed": report["passed"],
        "macro_accuracy": report["macro_accuracy"],
        "passed_cases": report["passed_cases"],
        "total_cases": report["total_cases"],
        "categories": report["categories"],
        "override_case_ids": sorted(report["override_audit"]["applied"]),
        "failed_case_ids": [
            item["case_id"] for item in report["failed_cases"]
        ],
    }, ensure_ascii=False, indent=2))
    return 1 if args.check and not report["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
