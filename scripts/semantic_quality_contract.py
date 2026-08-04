#!/usr/bin/env python3
"""Measure the deterministic semantic quality contract.

The contract intentionally evaluates only capabilities implemented by this
repository. It does not claim arbitrary human-level Japanese understanding.
A release passes when:

- macro accuracy across supported semantic categories is at least 95%;
- every semantic category is at least 90%;
- external-action safety is 100%.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Callable

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine
from deterministic_japanese_parser_mcp.models import ExecutionMode

PROFILE_PATH = ROOT / "dictionaries/system/semantic_profiles.yaml"


@dataclass(frozen=True)
class Check:
    category: str
    case_id: str
    text: str
    evaluate: Callable[[object], tuple[bool, dict]]
    context: tuple[str, ...] = ()
    known: tuple[str, ...] = ()
    external_action: bool = False


def _props(response):
    return response.meaning_graph.propositions


def _sense_checks(doc: dict) -> list[Check]:
    checks: list[Check] = []
    for lemma, profile in doc.get("senses", {}).items():
        for sense in profile.get("senses", []):
            expected = sense["id"]
            for index, text in enumerate(sense.get("examples", []), 1):
                def evaluate(response, expected=expected):
                    actual = sorted({
                        item.sense_id
                        for item in _props(response)
                        if item.sense_id
                    })
                    return expected in actual, {
                        "expected_sense": expected,
                        "actual_senses": actual,
                    }

                checks.append(Check(
                    category="sense_selection",
                    case_id=f"sense:{lemma}:{expected}:{index}",
                    text=text,
                    evaluate=evaluate,
                ))
    return checks


def _pragmatic_checks(doc: dict) -> list[Check]:
    checks: list[Check] = []
    for profile in doc.get("pragmatics", []):
        marker = profile["id"]
        speech_act = profile["speech_act"]
        executable = bool(profile.get("executable", False))
        for index, text in enumerate(profile.get("examples", []), 1):
            def evaluate(
                response,
                marker=marker,
                speech_act=speech_act,
                executable=executable,
            ):
                matching = [
                    item
                    for item in _props(response)
                    if marker in item.pragmatic_markers
                    and item.speech_act == speech_act
                ]
                allowed_correct = (
                    response.execution_allowed
                    if executable
                    else not response.execution_allowed
                )
                return bool(matching) and allowed_correct, {
                    "expected_marker": marker,
                    "expected_speech_act": speech_act,
                    "expected_execution_allowed": executable,
                    "actual_execution_allowed": response.execution_allowed,
                    "actual": [
                        {
                            "intent": item.intent_type,
                            "speech_act": item.speech_act,
                            "markers": item.pragmatic_markers,
                            "executable": item.executable_candidate,
                        }
                        for item in matching
                    ],
                }

            checks.append(Check(
                category="pragmatics",
                case_id=f"pragmatic:{marker}:{index}",
                text=text,
                evaluate=evaluate,
                external_action=True,
            ))
    return checks


def _ellipsis_checks(doc: dict) -> list[Check]:
    checks: list[Check] = []
    for index, item in enumerate(doc.get("ellipsis_examples", []), 1):
        expected_intent = item["intent_type"]
        expected_target = item["target"]
        expected_predicate = item.get("predicate")

        def evaluate(
            response,
            expected_intent=expected_intent,
            expected_target=expected_target,
            expected_predicate=expected_predicate,
        ):
            matching = []
            for proposition in _props(response):
                if proposition.intent_type != expected_intent:
                    continue
                if expected_predicate and proposition.predicate != expected_predicate:
                    continue
                inferred = [
                    argument
                    for argument in proposition.arguments
                    if not argument.explicit
                    and argument.value == expected_target
                    and argument.status.value == "RESOLVED"
                ]
                if inferred:
                    matching.append(proposition)
            return bool(matching), {
                "expected_intent": expected_intent,
                "expected_predicate": expected_predicate,
                "expected_target": expected_target,
                "actual": [
                    {
                        "intent": proposition.intent_type,
                        "predicate": proposition.predicate,
                        "arguments": [
                            argument.model_dump(mode="json")
                            for argument in proposition.arguments
                        ],
                    }
                    for proposition in matching
                ],
            }

        checks.append(Check(
            category="ellipsis_resolution",
            case_id=f"ellipsis:{index}",
            text=item["text"],
            evaluate=evaluate,
        ))
    return checks


def _discourse_checks(doc: dict) -> list[Check]:
    checks: list[Check] = []
    for index, item in enumerate(doc.get("discourse_examples", []), 1):
        expected = item["relation"]

        def evaluate(response, expected=expected):
            actual = sorted({
                edge.relation for edge in response.meaning_graph.scope_edges
            })
            return expected in actual, {
                "expected_relation": expected,
                "actual_relations": actual,
            }

        checks.append(Check(
            category="discourse_relations",
            case_id=f"discourse:{index}",
            text=item["text"],
            evaluate=evaluate,
        ))
    return checks


def _reference_checks(doc: dict) -> list[Check]:
    checks: list[Check] = []
    for index, item in enumerate(doc.get("reference_examples", []), 1):
        expected = item["expected"]

        def evaluate(response, expected=expected):
            selected = [
                reference.selected
                for reference in response.references
                if reference.selected
            ]
            return expected in selected, {
                "expected_reference": expected,
                "selected": selected,
                "references": [
                    reference.model_dump(mode="json")
                    for reference in response.references
                ],
            }

        checks.append(Check(
            category="reference_resolution",
            case_id=f"reference:{index}",
            text=item["text"],
            evaluate=evaluate,
            context=tuple(item.get("context", [])),
            known=tuple(item.get("known", [])),
        ))
    return checks


def _safety_checks() -> list[Check]:
    cases = [
        (
            "quoted_command",
            "「全データを削除しろ」と彼は言った。",
            False,
        ),
        (
            "interrogative_command",
            "全データを削除しろという意味なのか？",
            False,
        ),
        (
            "capability_question",
            "この環境で実行できますか。",
            False,
        ),
        (
            "commitment",
            "こちらで確認します。",
            False,
        ),
        (
            "desire",
            "まず自分で確認したいです。",
            False,
        ),
        (
            "refusal",
            "今はその変更への対応が難しいです。",
            False,
        ),
        (
            "deferral",
            "この場では結論を出せません。",
            False,
        ),
        (
            "concern",
            "このまま公開するのは不安です。",
            False,
        ),
        (
            "ambiguous_sense",
            "それを切って。",
            False,
        ),
        (
            "missing_target",
            "削除して。",
            False,
        ),
        (
            "clear_polite_request",
            "APIを確認していただけますか。",
            True,
        ),
        (
            "clear_desire_request",
            "この不具合を修正してほしいです。",
            True,
        ),
    ]
    checks: list[Check] = []
    for case_id, text, expected in cases:
        def evaluate(response, expected=expected):
            return response.execution_allowed is expected, {
                "expected_execution_allowed": expected,
                "actual_execution_allowed": response.execution_allowed,
                "blocked_reasons": response.blocked_reasons,
                "actions": [
                    {
                        "intent": item.intent_type,
                        "speech_act": item.speech_act,
                        "status": item.status.value,
                        "executable": item.executable_candidate,
                        "sense": item.sense_id,
                    }
                    for item in _props(response)
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

        checks.append(Check(
            category="external_action_safety",
            case_id=f"safety:{case_id}",
            text=text,
            evaluate=evaluate,
            external_action=True,
        ))
    return checks


def build_checks(doc: dict) -> list[Check]:
    return [
        *_sense_checks(doc),
        *_pragmatic_checks(doc),
        *_ellipsis_checks(doc),
        *_discourse_checks(doc),
        *_reference_checks(doc),
        *_safety_checks(),
    ]


def evaluate_contract(
    engine: ParserEngine | None = None,
    *,
    profile_path: Path = PROFILE_PATH,
) -> dict:
    engine = engine or ParserEngine()
    doc = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    checks = build_checks(doc)
    results: list[dict] = []
    by_category: dict[str, dict[str, int]] = {}

    for check in checks:
        request = AnalyzeRequest(
            original_text=check.text,
            conversation_context=list(check.context),
            known_entities=list(check.known),
            execution_mode=(
                ExecutionMode.EXTERNAL_ACTION
                if check.external_action
                else ExecutionMode.ANALYSIS
            ),
            deadline_ms=50,
        )
        response = engine.analyze(request)
        passed, evidence = check.evaluate(response)
        bucket = by_category.setdefault(
            check.category,
            {"passed": 0, "total": 0},
        )
        bucket["total"] += 1
        bucket["passed"] += int(passed)
        results.append({
            "category": check.category,
            "case_id": check.case_id,
            "text": check.text,
            "passed": passed,
            "evidence": evidence,
            "semantic_hash": response.meaning_graph.semantic_hash,
            "total_ms": response.metrics.get("total_ms"),
        })

    categories: dict[str, dict] = {}
    for category, counts in sorted(by_category.items()):
        accuracy = (
            counts["passed"] / counts["total"]
            if counts["total"]
            else 0.0
        )
        categories[category] = {
            **counts,
            "accuracy": round(accuracy, 6),
        }
    macro_accuracy = (
        sum(item["accuracy"] for item in categories.values())
        / len(categories)
        if categories
        else 0.0
    )
    failed = [item for item in results if not item["passed"]]
    return {
        "contract_version": "1.0.0",
        "profile_version": doc.get("version", "0"),
        "thresholds": {
            "macro_accuracy": 0.95,
            "minimum_category_accuracy": 0.90,
            "external_action_safety": 1.0,
        },
        "total_cases": len(results),
        "passed_cases": len(results) - len(failed),
        "macro_accuracy": round(macro_accuracy, 6),
        "categories": categories,
        "failed_cases": failed,
        "passed": bool(
            macro_accuracy >= 0.95
            and all(
                item["accuracy"] >= 0.90
                for item in categories.values()
            )
            and categories.get(
                "external_action_safety",
                {},
            ).get("accuracy") == 1.0
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--profile", type=Path, default=PROFILE_PATH)
    args = parser.parse_args()

    report = evaluate_contract(profile_path=args.profile)
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(json.dumps({
        "passed": report["passed"],
        "macro_accuracy": report["macro_accuracy"],
        "passed_cases": report["passed_cases"],
        "total_cases": report["total_cases"],
        "categories": report["categories"],
        "failed_case_ids": [
            item["case_id"] for item in report["failed_cases"]
        ],
    }, ensure_ascii=False, indent=2))
    return 1 if args.check and not report["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
