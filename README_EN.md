# Deterministic Japanese Parser MCP

<p align="center">
  <strong>A deterministic, non-LLM MCP parser that converts Japanese lexical, structural, semantic, contextual, and ambiguity evidence into reproducible machine-readable structures</strong>
</p>

<p align="center">
  <a href="README.md">日本語</a> ｜ <strong>English</strong>
</p>

<p align="center">
  <a href="https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP/actions/workflows/ci.yml/badge.svg"></a>
</p>

## Overview

Deterministic Japanese Parser MCP (DJPMCP) converts Japanese input into inspectable, reusable structures **before a human, Astera, an Agent, or a generative AI makes a downstream judgment**.

It does not reduce text to a single intent label. Its central `MeaningGraph` can preserve lexical candidates, entities, clauses, propositions, predicate-argument structure, dependency, scope, attribution, reference, discourse, sense candidates, and unresolved elements. When actionable instructions are present, the same semantic interpretation can produce a `TaskGraph` and a fail-closed external-action decision.

DJPMCP is not an answer-generation AI. It does not intentionally invent missing subjects, targets, senses, causal relations, rights, or provenance. Ambiguity, insufficient evidence, and unsupported interpretation remain explicit states.

## Highest-level product requirement

The highest-level requirement is to return the **necessary complete Japanese reading result within 0.5 seconds** without using an LLM at runtime and without deleting reading accuracy, `MeaningGraph` information, ambiguity retention, reading evidence, or fail-closed safety to achieve speed.

Existing stricter scoped targets such as `target_latency_ms=10` and `hard_deadline_ms=50` remain hot-path/internal contracts unless explicitly migrated. Production acceptance records hardware, warm/cold conditions, input-length class, concurrency, p50/p95/p99, and MCP/HTTP boundaries. No single percentile metric replaces the top-level 0.5-second product requirement.

## Current implementation vs fixed target architecture

| Item | Current baseline |
|---|---|
| Package version | `0.4.0` |
| MCP tool | `analyze_japanese` |
| MCP transports | stdio / Streamable HTTP |
| Parser REST API | `POST /v1/analyze` |
| Python API | `ParserEngine().analyze(AnalyzeRequest(...))` |
| Python | 3.10+ |
| Morphology | SudachiPy + SudachiDict Core |
| Runtime LLM | None |
| Runtime external dictionary API | None |
| MeaningGraph | reuse existing `2.3.0` core |
| TaskGraph / GraphGuard | reuse existing core |
| Program license | MIT |

The fixed target flow is:

```text
Original authority
→ safe normalization
→ Sudachi baseline
→ Japanese-function projections
→ multi-lane front router
→ progressive retrieval
→ hard constraints
→ soft ranking
→ syntax / sense resolution
→ recovery only when needed
→ bounded candidate lattice
→ whole-sentence Top-K / beam / Viterbi-style decode
→ margin / evidence gate
→ router re-evaluation
→ existing MeaningGraph 2.3.0
→ TaskGraph
→ GraphGuard
```

The authoritative target architecture is [`docs/PARSER_ARCHITECTURE.md`](docs/PARSER_ARCHITECTURE.md).

**Documentation is not implementation evidence.** A target layer is not complete until its source, tests, required full build/audit, performance evidence, regression evidence, and authorized runtime readback are closed.

## Architecture invariants

- original text remains authoritative and is never silently overwritten by normalization or recovery;
- unsupported meaning is not invented;
- ambiguity and unresolved states are preserved;
- runtime analysis remains deterministic and non-LLM;
- auxiliary evidence does not become semantic authority by association;
- Purpose/source roles are retrieval/permission hints, not final meaning authority;
- external actions fail closed when material uncertainty remains;
- rights and provenance are enforced at field/evidence level;
- semantic-hash compatibility is explicitly gated;
- logical responsibilities are not hard-wired one-to-one to physical databases.

## Canonical data and Japanese-function projections

The latest fixed design references **9,852,513 canonical processed records**.

The runtime does not treat that set as one undifferentiated store to scan for every request. The same canonical authority is projected into logical Japanese-language lanes:

1. `Orthography/Reading`
2. `Noun-Entity`
3. `Predicate-Inflection`
4. `Function Words`
5. `Connective-Modifier`
6. `Onomatopoeia`
7. `Multiword`
8. `Syntax-Case-Clause`
9. `Sense-Semantic Relation`
10. `Usage-Context-Pragmatics`
11. `Document Structure`
12. `Evidence-Provenance-Rights`

Domain, translation, sentiment, temporal/era, frequency, and source-specific labels are secondary facets rather than primary meaning-routing lanes.

Projection artifacts remain derived views/indexes, not competing authorities. Compatible bundle sets are bound by canonical/schema/projection/scoring versions and incompatible combinations must be rejected.

## Front router and progressive retrieval

The deterministic front router chooses which logical lanes, facets, and indexes are relevant to the input. It does not decide final meaning.

The target router keeps primary/secondary/fallback candidates and exposes trace material such as `router_decision`, `candidate_lanes`, `selected_lanes`, skipped-lane reasons, secondary facets, `fallback_reason`, retrieval limits, recovery need, and router/projection versions.

Conditions such as exact miss, OOV, suspicious segmentation, grammar conflict, or syntax conflict may escalate to fallback/recovery. The router is evaluated again after recovery.

Progressive retrieval is an efficiency architecture, not feature reduction.

## Purpose routing boundary

Purpose/source routing may provide retrieval hints, role masks, consumer allow/deny information, permission boundaries, provenance, ranking, and evidence metadata.

It must not become the sole meaning classifier, replace Japanese-function lanes, create lexical meaning from auxiliary evidence, bypass field-level rights/provenance, or convert unknown roles into implicit permission.

## Noisy and typo recovery

The target architecture does **not** build a giant database of possible typos and does not fuzzy-match the whole input by default.

```text
original input
→ safe normalization
→ exact/normal analysis
→ recovery only for unresolved/OOV/abnormal segmentation/conflict
→ bounded span candidates including relevant adjacent boundaries
→ surface/reading/alias/morphology/split-merge candidates
→ deterministic recovery cost
→ local candidate lattice
→ whole-sentence Top-K / beam / Viterbi-style decode
→ reading/POS/segmentation/syntax/sense/context/facet/evidence rerank
→ margin + evidence gate
→ resolved OR explicit ambiguous/unresolved result
```

Unknown or newly coined expressions are not automatically classified as typos. Only candidates that land on actual runtime surface/lemma/reading/alias evidence are promoted. The original input remains available. Recovery bounds and margins are calibrated from Golden/Noise/Latency benchmarks rather than fixed arbitrarily.

If recovery creates or changes actionable predicate/target/intent semantics, external action fails closed with a dedicated reason such as `RECOVERY_CHANGED_ACTION_SEMANTICS` until the required evidence is satisfied.

## MeaningGraph, TaskGraph and GraphGuard

The target architecture reuses the existing `MeaningGraph` `2.3.0`, `TaskGraph`, and `GraphGuard` rather than rewriting them from scratch.

`MeaningGraph` remains the semantic authority. `TaskGraph` is derived downstream. `GraphGuard` remains the final deterministic semantic-safety boundary for `execution_mode="external_action"`.

Parser `execution_allowed` is not provider/OS authorization or human approval. Actual external action requires a separate caller-side authorization/approval boundary.

DJPMCP itself does not perform external actions.

## Field-level rights and provenance

Rights and evidence are tracked at field/evidence level rather than inferred from a whole source record.

The target contract supports values such as `senses / examples / translations / relations / metrics / aliases` being traced through:

`evidence_id → source_id/version → field semantics → license/rights lane → allowed consumer/use → forbidden use`.

Auxiliary evidence may strengthen ranking or provenance without becoming lexical/sense authority. Unknown rights never become implicit permission.

## semantic_hash compatibility

The current `MeaningGraph` semantic hash covers graph content other than the `semantic_hash` field itself. Adding default graph fields can therefore alter hashes for previously stable inputs.

Recovery/Interpretation Evidence, Router Trace, and field-level evidence references must not be connected until a compatibility gate proves either:

1. the extension preserves the existing hashed semantic payload as required; or
2. an explicit graph/hash version migration is defined, tested, and released.

Unexpected hash drift is not accepted.

## MCP progressive output profiles

The target MCP transport supports:

```text
McpAnalyzeRequest = AnalyzeRequest + transport-only output_profile
output_profile = compact | standard | full
Default = compact
```

`output_profile` is transport-only and must be removed before constructing the core semantic `AnalyzeRequest`.

- `compact`: **default**, lightweight status, principal reading/proposition material, important ambiguity/missing information, action safety, and semantic hash.
- `standard`: progressively exposes more semantic structure, tasks, reading detail, and evidence-related information while withholding the heaviest transport detail where schema-compatible.
- `full`: explicitly requested existing complete `AnalyzeResponse` structured shape.

Profile selection must not change parser semantics, core request identity, cache identity, or `semantic_hash`. The text summary is derived from the full semantic result before transport projection. The semantic cache stores the full result rather than creating separate semantic identities per profile.

Profile byte/node/candidate exposure limits are benchmark-calibrated; output slimming is never used to weaken the internal `MeaningGraph`.

At this documentation point, the M0-1 profile design is fixed and has an assistant-side candidate self-test, but VPS source/runtime verification remains separate evidence.

## Current MCP input contract

The current core `AnalyzeRequest` includes:

| Field | Required | Default |
|---|---:|---|
| `original_text` | yes | — |
| `conversation_context` | no | `[]` |
| `known_entities` | no | `[]` |
| `protected_elements` | no | `[]` |
| `social_context` | no | empty model |
| `discourse_state` | no | `{}` |
| `execution_mode` | no | `analysis` |
| `analysis_depth` | no | `auto` |
| `deadline_ms` | no | `50` |

M0-1 adds `output_profile` only to the MCP transport request and does not add it to the core semantic request.

## Quick start

### Linux / macOS

```bash
git clone https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP.git
cd Deterministic-Japanese-Parser-MCP
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
djpmcp-validate
```

### Windows PowerShell

```powershell
git clone https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP.git
cd Deterministic-Japanese-Parser-MCP
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .
djpmcp-validate
```

For development:

```bash
pip install -e ".[dev]"
```

## MCP stdio

```bash
djpmcp
```

Example client configuration:

```json
{
  "mcpServers": {
    "deterministic-japanese-parser": {
      "command": "/absolute/path/Deterministic-Japanese-Parser-MCP/.venv/bin/djpmcp"
    }
  }
}
```

## Streamable HTTP / REST

```bash
export DJPMCP_HTTP_API_KEY='replace-with-a-long-random-secret'
djpmcp-http
```

Defaults:

```text
Host: 127.0.0.1
Port: 8765
MCP endpoint: /mcp
Parser REST endpoint: /v1/analyze
Health: /healthz
Readiness: /readyz
```

Protected endpoints accept Bearer authentication or `X-API-Key`. `/healthz` and `/readyz` remain public.

See [`docs/PRODUCTION_HTTP_DEPLOYMENT.md`](docs/PRODUCTION_HTTP_DEPLOYMENT.md) for production boundaries.

## Canonical data and runtime projections

```text
verified source
→ source adapter
→ schema / provenance / rights validation
→ review / decision ledger
→ canonical processed records
→ Japanese-function projection compiler
→ runtime bundles / indexes
```

The new projection architecture is not complete until input/output/rejected/unresolved accounting, rights/provenance audit, deterministic hashes, and all-record audit are closed.

See:

- [`docs/UNIFIED_SEMANTIC_DATA_PIPELINE.md`](docs/UNIFIED_SEMANTIC_DATA_PIPELINE.md)
- [`docs/OPEN_DICTIONARY_SUPPLY_CHAIN.md`](docs/OPEN_DICTIONARY_SUPPLY_CHAIN.md)
- [`docs/LANGUAGE_DATA_RUNTIME.md`](docs/LANGUAGE_DATA_RUNTIME.md)
- [`docs/DIRECT_FINAL_RUNTIME_DEPLOYMENT.md`](docs/DIRECT_FINAL_RUNTIME_DEPLOYMENT.md)

## Logical runtime bundles

Initial logical responsibilities:

- `router_core`
- `grammar_core`
- `lexical_semantic`
- `context_evidence`
- `recovery_index`

These are responsibility boundaries, not a requirement for five physical databases. Physical layout is benchmark-driven.

## Validation and completion

Final architecture evidence includes:

- MCP output-profile compatibility;
- semantic-hash compatibility;
- Router Trace;
- Recovery Interpretation Evidence;
- field-level rights/provenance;
- projection manifest/bundle compatibility;
- full 9,852,513-record rebuild and all-record audit;
- clean/noisy/typo/broken-input regression;
- proper noun/function word/connective/onomatopoeia/multiword/long-text coverage;
- router lane recall / false exclusion / OOV fallback;
- false-correction and ambiguity-retention metrics;
- recovered-action safety;
- field-rights integrity;
- MCP output size and recovery latency;
- production-representative 0.5-second complete-reading acceptance;
- full regression;
- authorized runtime deployment/readback.

Process start, HTTP 200, successful build, a finished test runner, or CI green alone is not semantic completion evidence.

## Fixed near-term implementation order

```text
M0-1 MCP compact / standard / full
→ targeted MCP tests
→ semantic_hash compatibility gate
→ Router Trace / Recovery Interpretation Evidence / Field-level Rights contract
→ Japanese-function Projection Compiler
→ Front multi-lane Router
→ existing MeaningGraph connection
→ Recovery Index / Lattice / Top-K
→ Progressive Context / Evidence Retrieval
→ 9.85M full build / audit
→ clean + noisy + typo + broken regression
→ false-correction / ambiguity-retention
→ 0.5-second complete-reading acceptance
→ full regression
→ authorized runtime readback
```

## Target-architecture status at this documentation update

| Area | Status |
|---|---|
| MeaningGraph / TaskGraph / GraphGuard | existing; reuse |
| MCP typed base | existing; reuse |
| semantic quality / holdout | existing; reuse |
| Direct Final manifest/hash | existing; reuse |
| Purpose routing | PARTIAL |
| MCP `compact/standard/full` | DESIGN FIXED / SELF-TEST CANDIDATE PASS / VPS SOURCE+RUNTIME NOT YET VERIFIED |
| semantic-hash compatibility gate | NOT IMPLEMENTED |
| Router Trace | NOT IMPLEMENTED |
| Recovery Evidence / Index / Lattice / Top-K | NOT IMPLEMENTED |
| field-level rights/provenance extension | NOT IMPLEMENTED |
| Japanese-function projection compiler | NOT IMPLEMENTED |
| Front multi-lane router | NOT IMPLEMENTED |
| Progressive Context Retrieval | NOT IMPLEMENTED |
| final 9.85M rebuild/audit | NOT RUN |
| final robustness | NOT RUN |
| final 0.5-second complete-reading acceptance | NOT RUN |
| final full regression | NOT RUN |
| target-architecture runtime deployment | NOT DEPLOYED |

`SELF-TEST CANDIDATE PASS` is assistant-side contract/projection/cache-identity validation and does not mean VPS source/runtime PASS.

## Public OSS and hosted service

DJPMCP supports public OSS/self-host operation and an official managed Astera service model. The hosted model adds platform responsibilities around the open parser core rather than defining a deliberately crippled parser edition.

Commercial platform responsibilities may include customer identity, credentials, authorization, metering, credit/quota, billing, rate limiting, tenant isolation, monitoring, rollout/rollback, support, and official Astera integration.

See:

- [`docs/COMMERCIAL_AND_DISTRIBUTION_MODEL.md`](docs/COMMERCIAL_AND_DISTRIBUTION_MODEL.md)
- [`docs/ASTERA_HOSTED_API_ARCHITECTURE.md`](docs/ASTERA_HOSTED_API_ARCHITECTURE.md)
- [`docs/PRODUCTION_HTTP_DEPLOYMENT.md`](docs/PRODUCTION_HTTP_DEPLOYMENT.md)

## Documentation map

Start with:

- [`docs/PARSER_ARCHITECTURE.md`](docs/PARSER_ARCHITECTURE.md) — authoritative overall target parser architecture
- [`docs/README.md`](docs/README.md) — documentation index

Core contracts:

- [`docs/JAPANESE_READING_CONTRACT.md`](docs/JAPANESE_READING_CONTRACT.md)
- [`docs/SEMANTIC_QUALITY_CONTRACT.md`](docs/SEMANTIC_QUALITY_CONTRACT.md)
- [`docs/UNIFIED_SEMANTIC_DATA_PIPELINE.md`](docs/UNIFIED_SEMANTIC_DATA_PIPELINE.md)
- [`docs/LANGUAGE_DATA_RUNTIME.md`](docs/LANGUAGE_DATA_RUNTIME.md)
- [`docs/OPEN_DICTIONARY_SUPPLY_CHAIN.md`](docs/OPEN_DICTIONARY_SUPPLY_CHAIN.md)
- [`docs/DIRECT_FINAL_RUNTIME_DEPLOYMENT.md`](docs/DIRECT_FINAL_RUNTIME_DEPLOYMENT.md)
- [`docs/PERFORMANCE_AND_RELEASE_CONTRACT.md`](docs/PERFORMANCE_AND_RELEASE_CONTRACT.md)

Policy and release:

- [`VALIDATION.md`](VALIDATION.md)
- [`CONTRIBUTING.md`](CONTRIBUTING.md)
- [`SECURITY.md`](SECURITY.md)
- [`GOVERNANCE.md`](GOVERNANCE.md)
- [`LICENSE`](LICENSE)
- [`NOTICE.md`](NOTICE.md)
- [`TRADEMARK.md`](TRADEMARK.md)

## Definition of done

The target architecture is complete only when documentation, source, tests, canonical build/audit, robustness, performance, full regression, and authorized runtime readback all agree.

Until then, each scope is reported separately as `PASS`, `FAIL`, `PARTIAL`, `BLOCKED`, `UNKNOWN`, `NOT_EXECUTED`, or `NOT_VERIFIED`.