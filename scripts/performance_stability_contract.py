#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys
from typing import Any


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        raise ValueError("performance denominator must be > 0")
    return numerator / denominator


def _series(reports: list[dict[str, Any]], *keys: str) -> list[float]:
    values: list[float] = []
    for report in reports:
        value: Any = report
        for key in keys:
            value = value[key]
        values.append(float(value))
    return values


def _spread_ratio(values: list[float]) -> float:
    low = min(values)
    high = max(values)
    if low <= 0:
        return float("inf") if high > 0 else 1.0
    return high / low


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate repeated performance-contract reports without weakening "
            "the existing absolute latency gates."
        )
    )
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--min-runs", type=int, default=3)
    parser.add_argument("--max-scale-ratio", type=float, default=2.5)
    parser.add_argument("--max-run-spread", type=float, default=2.5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if len(args.reports) < args.min_runs:
        parser.error(
            f"at least {args.min_runs} reports are required; got {len(args.reports)}"
        )

    reports = [_read(path) for path in args.reports]
    failures: list[str] = []

    short_base = _series(reports, "engine_short_warm", "p95_ms")
    short_stress = _series(reports, "stress_engine_short_warm", "p95_ms")
    complex_base = _series(reports, "engine_complex_warm", "p95_ms")
    complex_stress = _series(reports, "stress_engine_complex_warm", "p95_ms")
    stdio = _series(
        reports,
        "stdio",
        "low_latency_schema_safe",
        "steady_tool_call",
        "p95_ms",
    )

    short_scale_ratios = [
        _ratio(stress, base) for stress, base in zip(short_stress, short_base)
    ]
    complex_scale_ratios = [
        _ratio(stress, base) for stress, base in zip(complex_stress, complex_base)
    ]

    for label, ratios in (
        ("short", short_scale_ratios),
        ("complex", complex_scale_ratios),
    ):
        worst = max(ratios)
        if worst > args.max_scale_ratio:
            failures.append(
                f"scale=20 {label} p95 degradation ratio {worst:.3f} "
                f"exceeded {args.max_scale_ratio:.3f}"
            )

    spread_metrics = {
        "engine_short_warm_p95": _spread_ratio(short_base),
        "engine_complex_warm_p95": _spread_ratio(complex_base),
        "stress_engine_short_warm_p95": _spread_ratio(short_stress),
        "stress_engine_complex_warm_p95": _spread_ratio(complex_stress),
        "stdio_steady_p95": _spread_ratio(stdio),
    }
    unstable = {
        name: value
        for name, value in spread_metrics.items()
        if value > args.max_run_spread
    }
    if unstable:
        failures.append(
            "repeated-run spread exceeded stability bound: "
            + ", ".join(
                f"{name}={value:.3f}" for name, value in sorted(unstable.items())
            )
        )

    payload = {
        "run_count": len(reports),
        "absolute_contract_policy": (
            "Each input report must already come from performance_contract.py "
            "--check. This stability contract never converts an absolute failure "
            "into a pass."
        ),
        "max_scale_ratio": args.max_scale_ratio,
        "max_run_spread": args.max_run_spread,
        "scale_ratios": {
            "short": short_scale_ratios,
            "complex": complex_scale_ratios,
        },
        "run_spread": spread_metrics,
        "medians": {
            "engine_short_warm_p95_ms": statistics.median(short_base),
            "engine_complex_warm_p95_ms": statistics.median(complex_base),
            "stdio_steady_p95_ms": statistics.median(stdio),
        },
        "failures": failures,
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")

    if failures:
        print("PERFORMANCE STABILITY CONTRACT FAILED", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("PERFORMANCE STABILITY CONTRACT OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
