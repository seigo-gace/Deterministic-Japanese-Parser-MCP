#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path
from time import perf_counter

import regex
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine
from deterministic_japanese_parser_mcp.config import SETTINGS
from deterministic_japanese_parser_mcp.dictionaries import _load_json_set
from deterministic_japanese_parser_mcp.normalizer import normalize_with_map

METAPHOR_DIR = ROOT / "dictionaries/system/metaphors"
GOLD_DIR = ROOT / "tests/gold"
VALIDATION_HARD_DEADLINE_MS = 60_000
SEMANTIC_IMPACT_PREFIXES = (
    "src/",
    "dictionaries/",
    "rules/",
    "config/",
    "schemas/",
    "research/",
    "data/reviewed/",
    "scripts/",
    "tools/",
)
NON_SEMANTIC_PREFIXES = (
    "docs/",
    ".github/ISSUE_TEMPLATE/",
    ".github/PULL_REQUEST_TEMPLATE/",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deterministic dictionary, rule and Gold validation."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--gold-only",
        action="store_true",
        help="Run only the Gold semantic/parity gate.",
    )
    mode.add_argument(
        "--global-only",
        action="store_true",
        help="Run only dictionary/rule control validation.",
    )
    parser.add_argument("--batch", type=int, help="1-based Gold shard number.")
    parser.add_argument(
        "--total-batches",
        type=int,
        default=1,
        help="Total Gold shard count.",
    )
    parser.add_argument(
        "--changed-since",
        help=(
            "Conservatively select Gold cases affected since a git base SHA. "
            "Source/runtime changes fall back to the full Gold set."
        ),
    )
    parser.add_argument(
        "--selection-only",
        action="store_true",
        help="Print selected Gold IDs as JSON without running ParserEngine.",
    )
    parser.add_argument(
        "--skip-determinism",
        action="store_true",
        help="Skip the repeated-response determinism check for this shard.",
    )
    args = parser.parse_args(argv)
    if args.total_batches < 1:
        parser.error("--total-batches must be >= 1")
    if args.batch is not None and not 1 <= args.batch <= args.total_batches:
        parser.error("--batch must be between 1 and --total-batches")
    if args.batch is None and args.total_batches != 1:
        parser.error("--total-batches requires --batch")
    if args.global_only and (
        args.batch is not None
        or args.changed_since
        or args.selection_only
        or args.skip_determinism
    ):
        parser.error("Gold selection options cannot be combined with --global-only")
    return args


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_metaphors() -> list[dict]:
    return _load_json_set(METAPHOR_DIR).get("entries", [])


def validate_metaphor_controls() -> list[str]:
    errors: list[str] = []
    control_path = METAPHOR_DIR / "overrides.json"
    controls = _load_json(control_path) if control_path.exists() else {}
    allowed_overrides = set(controls.get("override_expressions", []))
    disabled = set(controls.get("disabled_expressions", []))

    occurrences: Counter[str] = Counter()
    for path in sorted(METAPHOR_DIR.glob("*.json")):
        if path.name in {"manifest.json", "overrides.json"}:
            continue
        for item in _load_json(path).get("entries", []):
            occurrences[item["expression"]] += 1

    for expression, count in sorted(occurrences.items()):
        if count > 1 and expression not in allowed_overrides:
            errors.append(
                f"undeclared metaphor override: {expression}: occurrences={count}"
            )
    for expression in sorted(allowed_overrides):
        if occurrences[expression] < 2:
            errors.append(
                f"declared metaphor override has no duplicate source: {expression}"
            )
    for expression in sorted(disabled):
        if occurrences[expression] == 0:
            errors.append(f"disabled metaphor source is missing: {expression}")

    final_expressions = {item["expression"] for item in load_metaphors()}
    for expression in disabled:
        if expression in final_expressions:
            errors.append(f"disabled metaphor remains active: {expression}")
    for item in controls.get("replacement_entries", []):
        if item["expression"] not in final_expressions:
            errors.append(
                f"replacement metaphor was not loaded: {item['expression']}"
            )
    for expression in controls.get("pattern_overrides", {}):
        if expression not in final_expressions:
            errors.append(
                f"pattern override target is not active: {expression}"
            )
    return errors


def load_rules() -> dict[str, list[dict]]:
    intents: dict[str, list[dict]] = {}
    for path in sorted((ROOT / "dictionaries/system/rules").glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for intent, items in doc.get("intents", {}).items():
            intents.setdefault(intent, []).extend(items or [])
    return intents


def _gold_files() -> list[Path]:
    return sorted(GOLD_DIR.glob("*.json"))


def load_gold(paths: set[Path] | None = None) -> list[dict]:
    by_id: dict[str, dict] = {}
    for path in _gold_files():
        if paths is not None and path.resolve() not in paths:
            continue
        doc = _load_json(path)
        allow_override = doc.get("override_policy") == "last_case_id_wins"
        for case in doc.get("cases", []):
            if case["id"] in by_id and not allow_override:
                raise ValueError(
                    f"duplicate Gold id without override policy: {case['id']}"
                )
            by_id[case["id"]] = case
    return list(by_id.values())


def semantic_response(response) -> dict:
    value = response.model_dump(mode="json")
    value.pop("metrics", None)
    return value


def _payload_hash(value) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def response_hash(response) -> str:
    return _payload_hash(semantic_response(response))


def request_from_case(case: dict) -> AnalyzeRequest:
    request = dict(case.get("request", {}))
    request.setdefault("original_text", case["text"])
    request.setdefault("deadline_ms", 60000)
    return AnalyzeRequest(**request)


def _rule_parity(engine: ParserEngine, request: AnalyzeRequest) -> tuple[dict, dict]:
    """Compare indexed/exhaustive rule extraction without rerunning full ParserEngine."""
    normalized, mapping = normalize_with_map(request.original_text)
    deadline_ms = min(request.deadline_ms, engine.settings.hard_deadline_ms)

    indexed, indexed_timeouts = engine.rules.extract(
        normalized,
        mapping,
        request.original_text,
        deadline_at=perf_counter() + deadline_ms / 1000,
    )
    exhaustive, exhaustive_timeouts = engine.rules.extract_exhaustive(
        normalized,
        mapping,
        request.original_text,
        deadline_at=perf_counter() + deadline_ms / 1000,
    )

    return (
        {
            "intents": [item.model_dump(mode="json") for item in indexed],
            "timeouts": indexed_timeouts,
        },
        {
            "intents": [item.model_dump(mode="json") for item in exhaustive],
            "timeouts": exhaustive_timeouts,
        },
    )


def _changed_files(base_sha: str) -> list[str] | None:
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base_sha}...HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _differential_gold_paths(
    changed_files: list[str] | None,
) -> tuple[set[Path] | None, str]:
    """Return a conservative Gold file selection.

    None means full Gold is required. An empty set means no Gold case is affected.
    Case-level dependency metadata does not yet exist, so any runtime/source change
    deliberately falls back to the complete 649-case gate.
    """
    if changed_files is None:
        return None, "git-diff-unavailable-full-fallback"
    if not changed_files:
        return set(), "no-changes"

    gold_changes = {
        (ROOT / path).resolve()
        for path in changed_files
        if path.startswith("tests/gold/") and path.endswith(".json")
    }
    other_changes = [
        path for path in changed_files if not path.startswith("tests/gold/")
    ]
    if gold_changes and not other_changes:
        return gold_changes, "changed-gold-files-only"

    if all(
        path.startswith(NON_SEMANTIC_PREFIXES) or path == "README.md"
        for path in changed_files
    ):
        return set(), "non-semantic-files-only"

    if any(path.startswith(SEMANTIC_IMPACT_PREFIXES) for path in changed_files):
        return None, "semantic-impact-full-fallback"

    return None, "unknown-impact-full-fallback"


def _select_gold(
    gold: list[dict],
    *,
    batch: int | None,
    total_batches: int,
) -> list[dict]:
    if batch is None:
        return gold
    shard_index = batch - 1
    return [
        case
        for index, case in enumerate(gold)
        if index % total_batches == shard_index
    ]


def _validate_global(errors: list[str]) -> tuple[int, int]:
    errors.extend(validate_metaphor_controls())
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
            errors.append(f"duplicate effective metaphor: {expression}")
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
            errors.append(f"invalid context_policy: {expression}: {policy}")

    manifest_path = METAPHOR_DIR / "manifest.json"
    if manifest_path.exists():
        manifest = _load_json(manifest_path)
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
    return len(metaphors), len(ids)


def _validate_gold(
    gold: list[dict],
    *,
    errors: list[str],
    run_determinism: bool,
) -> tuple[int, int]:
    validation_settings = replace(
        SETTINGS,
        hard_deadline_ms=max(
            SETTINGS.hard_deadline_ms,
            SETTINGS.target_latency_ms,
            VALIDATION_HARD_DEADLINE_MS,
        ),
    )
    engine = ParserEngine(settings=validation_settings)
    failures: list[dict] = []
    parity_failures: list[dict] = []

    for case in gold:
        request = request_from_case(case)
        indexed = engine.analyze(request)

        indexed_rules, exhaustive_rules = _rule_parity(engine, request)
        if indexed_rules != exhaustive_rules:
            parity_failures.append({
                "id": case["id"],
                "indexed_rule_hash": _payload_hash(indexed_rules),
                "exhaustive_rule_hash": _payload_hash(exhaustive_rules),
            })

        expected_doc = case["expected"]
        got_types = [item.type for item in indexed.intents]
        got_type_set = set(got_types)
        expected = set(expected_doc.get("intents", []))
        missing = expected - got_type_set
        forbidden = set(expected_doc.get("forbidden_intents", [])) & got_type_set
        exact_intents = expected_doc.get("exact_intents")
        exact_intent_mismatch = exact_intents is not None and got_types != exact_intents

        got_metaphor_list = [item.expression for item in indexed.metaphors]
        got_metaphors = set(got_metaphor_list)
        missing_metaphors = set(expected_doc.get("metaphors", [])) - got_metaphors
        duplicate_metaphors: list[str] = []
        if expected_doc.get("unique_metaphors"):
            counts = Counter(got_metaphor_list)
            duplicate_metaphors = sorted(
                item for item, count in counts.items() if count > 1
            )

        got_task_intents = [item.intent_type for item in indexed.tasks]
        missing_tasks = set(expected_doc.get("task_intents", [])) - set(got_task_intents)
        forbidden_tasks = set(expected_doc.get("forbidden_task_intents", [])) & set(
            got_task_intents
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
        errors.append(f"gold failures: {len(failures)} first={failures[:5]}")
    if parity_failures:
        errors.append(
            "indexed/exhaustive rule mismatch: "
            f"{len(parity_failures)} first={parity_failures[:5]}"
        )

    if run_determinism and gold:
        request = request_from_case(gold[-1])
        hashes = {response_hash(engine.analyze(request)) for _ in range(100)}
        if len(hashes) != 1:
            errors.append(f"non-deterministic response hashes: {sorted(hashes)}")

    return len(failures), len(parity_failures)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    errors: list[str] = []
    metaphor_count = 0
    rule_count = 0

    if not args.gold_only:
        metaphor_count, rule_count = _validate_global(errors)
        if args.global_only:
            if errors:
                print("VALIDATION FAILED")
                for error in errors:
                    print("-", error)
                return 1
            print(
                "GLOBAL VALIDATION OK: "
                f"metaphors={metaphor_count} rules={rule_count}"
            )
            return 0

    try:
        changed_files = _changed_files(args.changed_since) if args.changed_since else None
        selected_paths: set[Path] | None = None
        differential_reason = "full-gold"
        if args.changed_since:
            selected_paths, differential_reason = _differential_gold_paths(changed_files)
        gold = load_gold(selected_paths)
    except ValueError as exc:
        errors.append(str(exc))
        gold = []
        differential_reason = "load-error"

    selected_gold = _select_gold(
        gold,
        batch=args.batch,
        total_batches=args.total_batches,
    )

    if args.selection_only:
        print(json.dumps({
            "changed_since": args.changed_since,
            "differential_reason": differential_reason,
            "changed_files": changed_files if args.changed_since else None,
            "batch": args.batch,
            "total_batches": args.total_batches,
            "selected_count": len(selected_gold),
            "selected_ids": [case["id"] for case in selected_gold],
        }, ensure_ascii=False, sort_keys=True))
        return 1 if errors else 0

    failures = 0
    parity_failures = 0
    if selected_gold:
        failures, parity_failures = _validate_gold(
            selected_gold,
            errors=errors,
            run_determinism=not args.skip_determinism,
        )

    if errors:
        print("VALIDATION FAILED")
        for error in errors:
            print("-", error)
        return 1

    batch_label = "all" if args.batch is None else f"{args.batch}/{args.total_batches}"
    print(
        "VALIDATION OK: "
        f"metaphors={metaphor_count} rules={rule_count} "
        f"gold={len(selected_gold)} batch={batch_label} "
        f"differential={differential_reason} "
        f"failures={failures} parity_failures={parity_failures}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
