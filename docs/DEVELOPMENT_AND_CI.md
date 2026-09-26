# Development and CI / 開発・CIリファレンス

Version 1.0 — 2026-09-26

## Supported Python

CI matrix:

```text
Python 3.10
Python 3.12
```

## Development Install

```bash
pip install -e ".[dev]"
```

## Main Validation Commands

```bash
python scripts/preflight.py
python tools/lexicon_validator.py
python tools/validator.py
python scripts/semantic_quality_contract.py --check
python scripts/semantic_holdout_contract.py --check
pytest
python scripts/benchmark.py --check --rounds 50
python scripts/performance_contract.py --check --rounds 50 --stdio-rounds 30 --scale 20 --max-ready-ms 10
python scripts/astera_latency_contract.py --check --rounds 50 --stdio-rounds 30 --target-ms 10 --hard-ms 50
python -m compileall -q src tools scripts tests
```

## Public CI Gates

Current `.github/workflows/ci.yml` verifies:

1. Deployment preflight
2. Runtime lexicon provenance and license validation
3. Dictionary / Gold validation
4. Supported semantic profile quality contract
5. Independent semantic holdout contract
6. Unit / importer / supply-chain / MCP stdio E2E tests
7. Benchmark regression
8. 10ms target + 20x dictionary performance contract
9. Astera call-through 10ms target / 50ms hard limit
10. `compileall`
11. Evidence artifact preservation

The performance thresholds are project contracts. Do not weaken them to make CI green.

## Evidence

CI preserves reports as GitHub Actions artifacts. When publishing a measured performance or quality result, record the matching:

- Commit SHA
- Workflow run
- Python version
- Artifact digest

Unverified local measurements should not be presented as official project results.

## Baseline First

Before a behavior or performance change, record the current `main` result. If `main` is already failing a gate, separate that baseline failure from regressions introduced by the proposed change.

## README Runtime Examples

`scripts/readme_examples.py` executes the documented examples against the real `ParserEngine` and writes:

```text
reports/readme-examples.json
reports/readme-examples-compact.json
```

README sample values must be derived from this script rather than manually invented.
