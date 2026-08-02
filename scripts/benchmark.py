#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine
from deterministic_japanese_parser_mcp.normalizer import normalize_with_map


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


def stats(values: list[float]) -> dict[str, float | int]:
    return {
        "n": len(values),
        "p50_ms": round(percentile(values, 0.50), 3),
        "p95_ms": round(percentile(values, 0.95), 3),
        "p99_ms": round(percentile(values, 0.99), 3),
        "mean_ms": round(statistics.mean(values), 3),
        "max_ms": round(max(values), 3),
    }


def measure(function, rounds: int) -> list[float]:
    values: list[float] = []
    for _ in range(rounds):
        started = time.perf_counter()
        function()
        values.append((time.perf_counter() - started) * 1000)
    return values


def semantic(response) -> dict:
    value = response.model_dump(mode="json")
    value.pop("metrics", None)
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--rounds", type=int, default=100)
    args = parser.parse_args()

    engine = ParserEngine()
    short = "今のUIは殺すな。APIだけ変更しろ。"
    complex_text = (
        "障害の火消しをして、落ち着いてから穴を全部塞げ。"
        "最後にGitHubへ入れろ。"
    )
    protected = (
        "`ｶﾞ` https://example.com/path?q=1 " * 500
    )[:20000]
    unmatched = "あ" * 20000

    normalized_unmatched, mapping_unmatched = normalize_with_map(unmatched)
    parity: dict[str, bool] = {}
    for name, text in {
        "short": short,
        "complex": complex_text,
        "unmatched": "あ" * 500,
    }.items():
        request = AnalyzeRequest(original_text=text, deadline_ms=60000)
        indexed = engine.analyze(request)
        exhaustive = engine.analyze(request, exhaustive_rules=True)
        parity[name] = semantic(indexed) == semantic(exhaustive)

    report = {
        "normalization_protected_20k": stats(measure(
            lambda: normalize_with_map(protected),
            max(10, args.rounds // 5),
        )),
        "rules_indexed_unmatched_20k": stats(measure(
            lambda: engine.rules.extract(
                normalized_unmatched,
                mapping_unmatched,
                unmatched,
                deadline_at=time.perf_counter() + 60,
            ),
            max(10, args.rounds // 5),
        )),
        "rules_exhaustive_unmatched_20k": stats(measure(
            lambda: engine.rules.extract_exhaustive(
                normalized_unmatched,
                mapping_unmatched,
                unmatched,
                deadline_at=time.perf_counter() + 60,
            ),
            max(10, args.rounds // 5),
        )),
        "engine_short_warm": stats(measure(
            lambda: engine.analyze(AnalyzeRequest(
                original_text=short,
                deadline_ms=60000,
            )),
            args.rounds,
        )),
        "engine_complex_warm": stats(measure(
            lambda: engine.analyze(AnalyzeRequest(
                original_text=complex_text,
                deadline_ms=60000,
            )),
            args.rounds,
        )),
        "rule_metrics": engine.rules.last_metrics,
        "semantic_parity": parity,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if not args.check:
        return 0

    failures: list[str] = []
    if not all(parity.values()):
        failures.append(f"semantic parity failed: {parity}")
    if report["normalization_protected_20k"]["p95_ms"] >= 250:
        failures.append(
            "protected 20k normalization p95 must remain below 250 ms"
        )
    indexed_p95 = report["rules_indexed_unmatched_20k"]["p95_ms"]
    exhaustive_p95 = report["rules_exhaustive_unmatched_20k"]["p95_ms"]
    if indexed_p95 > exhaustive_p95 * 0.90:
        failures.append(
            "indexed unmatched-rule p95 did not improve by at least 10%: "
            f"{indexed_p95} vs {exhaustive_p95}"
        )
    if report["engine_short_warm"]["p95_ms"] >= 250:
        failures.append("short warm engine p95 must remain below 250 ms")
    metrics = report["rule_metrics"]
    if metrics["candidate_rule_count"] > metrics["total_rule_count"]:
        failures.append("candidate rule count exceeds total rule count")

    if failures:
        print("BENCHMARK CHECK FAILED", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("BENCHMARK CHECK OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
