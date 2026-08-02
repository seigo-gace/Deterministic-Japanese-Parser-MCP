#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import regex
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine


def load_metaphors() -> list[dict]:
    entries: list[dict] = []
    for path in sorted((ROOT / "dictionaries/system/metaphors").glob("*.json")):
        if path.name == "manifest.json":
            continue
        entries.extend(
            json.loads(path.read_text(encoding="utf-8")).get("entries", [])
        )
    return entries


def load_rules() -> dict[str, list[dict]]:
    intents: dict[str, list[dict]] = {}
    for path in sorted((ROOT / "dictionaries/system/rules").glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for intent, items in doc.get("intents", {}).items():
            intents.setdefault(intent, []).extend(items or [])
    return intents


def load_gold() -> list[dict]:
    cases: list[dict] = []
    for path in sorted((ROOT / "tests/gold").glob("*.json")):
        cases.extend(
            json.loads(path.read_text(encoding="utf-8")).get("cases", [])
        )
    return cases


def semantic_response(response) -> dict:
    value = response.model_dump(mode="json")
    value.pop("metrics", None)
    return value


def response_hash(response) -> str:
    encoded = json.dumps(
        semantic_response(response),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def request_from_case(case: dict) -> AnalyzeRequest:
    request = dict(case.get("request", {}))
    request.setdefault("original_text", case["text"])
    request.setdefault("deadline_ms", 60000)
    return AnalyzeRequest(**request)


def main() -> int:
    errors: list[str] = []
    metaphors = load_metaphors()
    seen: set[str] = set()
    surface_owner: dict[str, str] = {}
    for entry in metaphors:
        for key in (
            "expression",
            "interpretation",
            "context",
            "domain",
            "version",
        ):
            if key not in entry:
                errors.append(f"metaphor missing {key}: {entry}")
        expression = entry.get("expression")
        if expression in seen:
            errors.append(f"duplicate metaphor: {expression}")
        seen.add(expression)
        for surface in [expression, *entry.get("aliases", [])]:
            owner = surface_owner.get(surface)
            if owner and owner != expression:
                errors.append(
                    f"metaphor surface collision: {surface}: {owner} / {expression}"
                )
            surface_owner[surface] = expression
        policy = entry.get("context_policy", "optional")
        if policy not in {"optional", "required_any", "forbidden_any"}:
            errors.append(
                f"invalid context_policy: {expression}: {policy}"
            )

    manifest_path = ROOT / "dictionaries/system/metaphors/manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("metaphor_entries") != len(metaphors):
            errors.append(
                "manifest metaphor count mismatch: "
                f"{manifest.get('metaphor_entries')} != {len(metaphors)}"
            )

    rules = load_rules()
    ids: set[str] = set()
    for intent, items in rules.items():
        for item in items:
            if item["id"] in ids:
                errors.append(f"duplicate rule id: {item['id']}")
            ids.add(item["id"])
            try:
                regex.compile(item["pattern"])
            except Exception as exc:
                errors.append(f"bad regex {item['id']}: {exc}")

    engine = ParserEngine()
    gold = load_gold()
    failures: list[dict] = []
    parity_failures: list[dict] = []
    for case in gold:
        request = request_from_case(case)
        indexed = engine.analyze(request)
        exhaustive = engine.analyze(request, exhaustive_rules=True)
        if semantic_response(indexed) != semantic_response(exhaustive):
            parity_failures.append({
                "id": case["id"],
                "indexed_hash": response_hash(indexed),
                "exhaustive_hash": response_hash(exhaustive),
            })

        expected_doc = case["expected"]
        got_types = [item.type for item in indexed.intents]
        got_type_set = set(got_types)
        expected = set(expected_doc.get("intents", []))
        missing = expected - got_type_set
        forbidden = (
            set(expected_doc.get("forbidden_intents", [])) & got_type_set
        )
        exact_intents = expected_doc.get("exact_intents")
        exact_intent_mismatch = (
            exact_intents is not None and got_types != exact_intents
        )

        got_metaphor_list = [item.expression for item in indexed.metaphors]
        got_metaphors = set(got_metaphor_list)
        missing_metaphors = (
            set(expected_doc.get("metaphors", [])) - got_metaphors
        )
        duplicate_metaphors: list[str] = []
        if expected_doc.get("unique_metaphors"):
            duplicate_metaphors = sorted({
                item
                for item in got_metaphor_list
                if got_metaphor_list.count(item) > 1
            })

        got_task_intents = [item.intent_type for item in indexed.tasks]
        missing_tasks = (
            set(expected_doc.get("task_intents", []))
            - set(got_task_intents)
        )
        forbidden_tasks = (
            set(expected_doc.get("forbidden_task_intents", []))
            & set(got_task_intents)
        )
        exact_tasks = expected_doc.get("exact_task_targets")
        exact_task_mismatch = (
            exact_tasks is not None
            and [item.target for item in indexed.tasks] != exact_tasks
        )

        expected_overall = expected_doc.get("overall_status")
        overall_mismatch = (
            expected_overall is not None
            and indexed.overall_status.value != expected_overall
        )
        expected_allowed = expected_doc.get("execution_allowed")
        guard_mismatch = (
            expected_allowed is not None
            and indexed.execution_allowed != expected_allowed
        )

        if (
            missing
            or forbidden
            or exact_intent_mismatch
            or missing_metaphors
            or duplicate_metaphors
            or missing_tasks
            or forbidden_tasks
            or exact_task_mismatch
            or overall_mismatch
            or guard_mismatch
        ):
            failures.append({
                "id": case["id"],
                "missing_intents": sorted(missing),
                "forbidden_intents": sorted(forbidden),
                "exact_intent_mismatch": exact_intent_mismatch,
                "missing_metaphors": sorted(missing_metaphors),
                "duplicate_metaphors": duplicate_metaphors,
                "missing_task_intents": sorted(missing_tasks),
                "forbidden_task_intents": sorted(forbidden_tasks),
                "exact_task_mismatch": exact_task_mismatch,
                "overall_mismatch": overall_mismatch,
                "guard_mismatch": guard_mismatch,
                "got": got_types,
                "got_tasks": got_task_intents,
            })

    if failures:
        errors.append(
            f"gold failures: {len(failures)} first={failures[:5]}"
        )
    if parity_failures:
        errors.append(
            "indexed/exhaustive response mismatch: "
            f"{len(parity_failures)} first={parity_failures[:5]}"
        )

    if gold:
        request = request_from_case(gold[-1])
        hashes = {
            response_hash(engine.analyze(request))
            for _ in range(100)
        }
        if len(hashes) != 1:
            errors.append(
                f"non-deterministic response hashes: {sorted(hashes)}"
            )

    if errors:
        print("VALIDATION FAILED")
        for error in errors:
            print("-", error)
        return 1

    print(
        "VALIDATION OK: "
        f"metaphors={len(metaphors)} rules={len(ids)} gold={len(gold)} "
        f"indexed_rules={engine.rules.last_metrics['indexed_rule_count']} "
        f"always_scan={engine.rules.last_metrics['always_scan_rule_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
