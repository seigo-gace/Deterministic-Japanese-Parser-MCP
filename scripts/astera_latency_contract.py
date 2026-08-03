#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import statistics
import sys
import time

from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client

from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine
from deterministic_japanese_parser_mcp.low_latency_client import LowLatencyClientSession

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = [
    "APIだけ変更しろ。UIは維持する。",
    "テストが通ったらAPIを公開しろ。",
    "障害の火消しをして、落ち着いてから穴を塞げ。最後にGitHubへ入れろ。",
]


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


def measure_engine(rounds: int) -> dict[str, dict]:
    engine = ParserEngine()
    requests = [
        AnalyzeRequest(
            original_text=text,
            execution_mode="external_action",
            deadline_ms=50,
        )
        for text in SAMPLES
    ]
    for request in requests:
        engine.analyze(request)
    report: dict[str, dict] = {}
    for index, request in enumerate(requests, 1):
        values: list[float] = []
        semantic_hashes: set[str] = set()
        for _ in range(rounds):
            started = time.perf_counter_ns()
            response = engine.analyze(request)
            values.append((time.perf_counter_ns() - started) / 1_000_000)
            semantic_hashes.add(response.meaning_graph.semantic_hash)
            if not response.meaning_graph.propositions:
                raise RuntimeError("MeaningGraph contained no propositions")
        if len(semantic_hashes) != 1:
            raise RuntimeError("semantic hash changed across identical calls")
        report[f"sample_{index}"] = stats(values)
    return report


async def measure_stdio(rounds: int) -> dict:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "deterministic_japanese_parser_mcp.server"],
        cwd=ROOT,
    )
    async with stdio_client(parameters) as (read, write):
        async with LowLatencyClientSession(read, write) as session:
            await session.initialize()
            await session.prepare_tools()
            arguments = {
                "original_text": SAMPLES[0],
                "execution_mode": "external_action",
                "deadline_ms": 50,
            }
            first_started = time.perf_counter_ns()
            first = await session.call_tool(
                "analyze_japanese",
                arguments=arguments,
            )
            first_ms = (time.perf_counter_ns() - first_started) / 1_000_000
            structured = first.structuredContent
            if structured is None:
                raise RuntimeError("structured MCP response is required")
            if not structured.get("meaning_graph", {}).get("semantic_hash"):
                raise RuntimeError("MeaningGraph semantic_hash is missing")
            for _ in range(10):
                await session.call_tool(
                    "analyze_japanese",
                    arguments=arguments,
                )
            values: list[float] = []
            hashes: set[str] = set()
            for _ in range(rounds):
                started = time.perf_counter_ns()
                result = await session.call_tool(
                    "analyze_japanese",
                    arguments=arguments,
                )
                values.append((time.perf_counter_ns() - started) / 1_000_000)
                payload = result.structuredContent
                if payload is None:
                    raise RuntimeError("structured MCP response is required")
                hashes.add(payload["meaning_graph"]["semantic_hash"])
            if len(hashes) != 1:
                raise RuntimeError(
                    "stdio semantic hash changed across identical calls"
                )
    return {
        "first_call_ms": round(first_ms, 3),
        "steady_call": stats(values),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--rounds", type=int, default=100)
    parser.add_argument("--stdio-rounds", type=int, default=50)
    parser.add_argument("--target-ms", type=float, default=10.0)
    parser.add_argument("--hard-ms", type=float, default=50.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = {
        "contract": {
            "target_ms": args.target_ms,
            "hard_max_ms": args.hard_ms,
            "boundary": (
                "Astera-side call start through fully decoded and precompiled-"
                "schema-validated MeaningGraph, TaskGraph, and Guard result on "
                "persistent local stdio"
            ),
        },
        "engine": measure_engine(args.rounds),
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
    for name, values in report["engine"].items():
        if values["p95_ms"] > args.target_ms:
            failures.append(
                f"{name} p95 exceeded target {args.target_ms:.3f} ms: "
                f"{values['p95_ms']:.3f} ms"
            )
        if values["max_ms"] > args.hard_ms:
            failures.append(
                f"{name} max exceeded hard limit {args.hard_ms:.3f} ms: "
                f"{values['max_ms']:.3f} ms"
            )
    stdio = report["stdio"]
    if stdio["steady_call"]["p95_ms"] > args.target_ms:
        failures.append(
            "stdio p95 exceeded target "
            f"{args.target_ms:.3f} ms: "
            f"{stdio['steady_call']['p95_ms']:.3f} ms"
        )
    if stdio["first_call_ms"] > args.hard_ms:
        failures.append(
            f"stdio first call exceeded hard limit {args.hard_ms:.3f} ms: "
            f"{stdio['first_call_ms']:.3f} ms"
        )
    if stdio["steady_call"]["max_ms"] > args.hard_ms:
        failures.append(
            "stdio max exceeded hard limit "
            f"{args.hard_ms:.3f} ms: "
            f"{stdio['steady_call']['max_ms']:.3f} ms"
        )
    if failures:
        print("ASTERA LATENCY CONTRACT FAILED", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("ASTERA LATENCY CONTRACT OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
