#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import statistics
import sys
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent

from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine
from deterministic_japanese_parser_mcp.metaphor import MetaphorMatcher
from deterministic_japanese_parser_mcp.normalizer import normalize_with_map
from deterministic_japanese_parser_mcp.rule_engine import RuleEngine

ROOT = Path(__file__).resolve().parents[1]
SHORT_TEXT = "UIは残せ。APIだけ変更しろ。"
COMPLEX_TEXT = (
    "障害の火消しをして、落ち着いてから穴を全部塞げ。"
    "最後にGitHubへ入れろ。"
)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(len(ordered) * fraction)))
    return ordered[index]


def stats(values: list[float]) -> dict[str, float | int]:
    return {
        "n": len(values),
        "p50_ms": round(percentile(values, 0.50), 3),
        "p95_ms": round(percentile(values, 0.95), 3),
        "p99_ms": round(percentile(values, 0.99), 3),
        "mean_ms": round(statistics.mean(values), 3),
        "max_ms": round(max(values), 3),
    }


def measure(function, rounds: int, warmups: int = 10) -> list[float]:
    for _ in range(warmups):
        function()
    values: list[float] = []
    for _ in range(rounds):
        started = time.perf_counter_ns()
        function()
        values.append((time.perf_counter_ns() - started) / 1_000_000)
    return values


def semantic(response) -> dict:
    value = response.model_dump(mode="json")
    value.pop("metrics", None)
    return value


def expand_rules(doc: dict, scale: int) -> dict:
    expanded = deepcopy(doc)
    base_count = sum(len(items) for items in expanded.get("intents", {}).values())
    extra_count = max(0, base_count * (scale - 1))
    bucket = expanded.setdefault("intents", {}).setdefault("modify", [])
    for index in range(extra_count):
        literal = f"負荷試験専用規則{index:06d}"
        bucket.append({
            "id": f"STRESS-RULE-{index:06d}",
            "pattern": f"(?P<target>{literal})",
            "priority": 1,
            "enabled": True,
        })
    return expanded


def expand_metaphors(doc: dict, scale: int) -> dict:
    expanded = deepcopy(doc)
    entries = expanded.setdefault("entries", [])
    base_count = len(entries)
    extra_count = max(0, base_count * (scale - 1))
    for index in range(extra_count):
        entries.append({
            "expression": f"負荷試験専用比喩{index:06d}",
            "interpretation": f"負荷試験解釈{index:06d}",
            "domain": "stress-test",
            "context": [],
            "context_policy": "optional",
        })
    return expanded


def build_stress_engine(base: ParserEngine, scale: int) -> ParserEngine:
    stress = ParserEngine(settings=base.settings)
    stress.rules = RuleEngine(
        expand_rules(base.bundle.rules, scale),
        timeout_ms=base.settings.regex_timeout_ms,
    )
    stress.metaphors = MetaphorMatcher(
        expand_metaphors(base.bundle.metaphors, scale),
        timeout_ms=base.settings.regex_timeout_ms,
    )
    return stress


def validate_structured_result(result) -> dict:
    if result.isError:
        raise RuntimeError(f"MCP tool returned an error: {result}")
    structured = getattr(result, "structuredContent", None)
    if structured is None:
        structured = getattr(result, "structured_content", None)
    if structured is None:
        blocks = [item.text for item in result.content if isinstance(item, TextContent)]
        if not blocks:
            raise RuntimeError("MCP response contained no structured result")
        structured = json.loads(blocks[0])
    if structured.get("original_text") != SHORT_TEXT:
        raise RuntimeError("MCP response did not preserve original_text")
    intent_types = {item["type"] for item in structured.get("intents", [])}
    if not {"preserve", "modify"} <= intent_types:
        raise RuntimeError(f"MCP response lost required intents: {intent_types}")
    return structured


async def measure_stdio(rounds: int) -> dict:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "deterministic_japanese_parser_mcp.server"],
        cwd=ROOT,
    )
    process_started = time.perf_counter_ns()
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            initialized_ms = (time.perf_counter_ns() - process_started) / 1_000_000
            tools = await session.list_tools()
            if "analyze_japanese" not in {tool.name for tool in tools.tools}:
                raise RuntimeError("analyze_japanese was not exposed by the MCP server")

            arguments = {
                "original_text": SHORT_TEXT,
                "execution_mode": "external_action",
                "deadline_ms": 60000,
            }
            first_started = time.perf_counter_ns()
            first_result = await session.call_tool("analyze_japanese", arguments=arguments)
            first_ms = (time.perf_counter_ns() - first_started) / 1_000_000
            validate_structured_result(first_result)

            for _ in range(10):
                validate_structured_result(
                    await session.call_tool("analyze_japanese", arguments=arguments)
                )

            values: list[float] = []
            for _ in range(rounds):
                started = time.perf_counter_ns()
                result = await session.call_tool("analyze_japanese", arguments=arguments)
                validate_structured_result(result)
                values.append((time.perf_counter_ns() - started) / 1_000_000)

    return {
        "process_start_to_initialized_ms": round(initialized_ms, 3),
        "first_ready_tool_call_ms": round(first_ms, 3),
        "steady_tool_call": stats(values),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--rounds", type=int, default=100)
    parser.add_argument("--stdio-rounds", type=int, default=50)
    parser.add_argument("--scale", type=int, default=20)
    parser.add_argument("--max-ready-ms", type=float, default=5.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.scale < 1:
        parser.error("--scale must be at least 1")

    base = ParserEngine()
    base_request = AnalyzeRequest(original_text=SHORT_TEXT, deadline_ms=60000)
    complex_request = AnalyzeRequest(original_text=COMPLEX_TEXT, deadline_ms=60000)
    base.analyze(base_request)
    base.analyze(complex_request)

    stress_started = time.perf_counter_ns()
    stress = build_stress_engine(base, args.scale)
    stress_build_ms = (time.perf_counter_ns() - stress_started) / 1_000_000

    parity = {
        "short": semantic(base.analyze(base_request)) == semantic(stress.analyze(base_request)),
        "complex": semantic(base.analyze(complex_request)) == semantic(stress.analyze(complex_request)),
    }

    unmatched = "あ" * 20000
    normalized, mapping = normalize_with_map(unmatched)

    report = {
        "contract": {
            "ready_request_limit_ms": args.max_ready_ms,
            "dictionary_scale": args.scale,
            "boundary": "client call_tool start to fully decoded MCP result on persistent local stdio",
            "cold_start_is_separate": True,
        },
        "runtime": {
            "tokenizer_backend": base.tokenizer.backend,
            "base_rule_count": len(base.rules.compiled),
            "stress_rule_count": len(stress.rules.compiled),
            "base_metaphor_count": len(base.metaphors.entries),
            "stress_metaphor_count": len(stress.metaphors.entries),
            "stress_index_build_ms": round(stress_build_ms, 3),
        },
        "semantic_parity": parity,
        "engine_short_warm": stats(measure(
            lambda: base.analyze(base_request), args.rounds
        )),
        "engine_complex_warm": stats(measure(
            lambda: base.analyze(complex_request), args.rounds
        )),
        "stress_engine_short_warm": stats(measure(
            lambda: stress.analyze(base_request), args.rounds
        )),
        "stress_engine_complex_warm": stats(measure(
            lambda: stress.analyze(complex_request), args.rounds
        )),
        "stress_rule_index_unmatched_20k": stats(measure(
            lambda: stress.rules.candidate_indices(normalized),
            max(20, args.rounds // 2),
        )),
        "stress_metaphor_index_unmatched_20k": stats(measure(
            lambda: stress.metaphors._literal_matches(normalized),
            max(20, args.rounds // 2),
        )),
        "stdio": asyncio.run(measure_stdio(args.stdio_rounds)),
    }

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")

    if not args.check:
        return 0

    failures: list[str] = []
    if base.tokenizer.backend != "sudachi-core":
        failures.append(f"production tokenizer unavailable: {base.tokenizer.backend}")
    if not all(parity.values()):
        failures.append(f"expanded dictionaries changed semantic results: {parity}")

    expected_rule_count = len(base.rules.compiled) * args.scale
    expected_metaphor_count = len(base.metaphors.entries) * args.scale
    if len(stress.rules.compiled) != expected_rule_count:
        failures.append(
            f"stress rule count mismatch: {len(stress.rules.compiled)} != {expected_rule_count}"
        )
    if len(stress.metaphors.entries) != expected_metaphor_count:
        failures.append(
            "stress metaphor count mismatch: "
            f"{len(stress.metaphors.entries)} != {expected_metaphor_count}"
        )

    ready_metrics = {
        "engine_short_warm": report["engine_short_warm"]["p95_ms"],
        "engine_complex_warm": report["engine_complex_warm"]["p95_ms"],
        "stress_engine_short_warm": report["stress_engine_short_warm"]["p95_ms"],
        "stress_engine_complex_warm": report["stress_engine_complex_warm"]["p95_ms"],
        "stdio_first_ready_tool_call": report["stdio"]["first_ready_tool_call_ms"],
        "stdio_steady_tool_call": report["stdio"]["steady_tool_call"]["p95_ms"],
    }
    for name, value in ready_metrics.items():
        if value > args.max_ready_ms:
            failures.append(
                f"{name} p95/first exceeded {args.max_ready_ms:.3f} ms: {value:.3f} ms"
            )

    for name in (
        "stress_rule_index_unmatched_20k",
        "stress_metaphor_index_unmatched_20k",
    ):
        value = report[name]["p95_ms"]
        if value > args.max_ready_ms:
            failures.append(
                f"{name} p95 exceeded {args.max_ready_ms:.3f} ms: {value:.3f} ms"
            )

    if failures:
        print("PERFORMANCE CONTRACT FAILED", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("PERFORMANCE CONTRACT OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
