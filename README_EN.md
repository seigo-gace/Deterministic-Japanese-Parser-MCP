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

Deterministic Japanese Parser MCP (DJPMCP) converts Japanese input into inspectable, reusable structures **before a human or generative AI makes a downstream judgment**.

The parser does not reduce the text to a single intent label. Its central `MeaningGraph` can preserve lexical candidates, entities, clauses, propositions, predicate-argument structure, dependency, semantic scope, attribution, reference, discourse, sense candidates, and unresolved elements. When actionable instructions are present, the same semantic interpretation can produce a `TaskGraph` and a fail-closed external-action decision.

DJPMCP is not an answer-generation AI. It does not intentionally invent missing subjects, targets, senses, causal relations, rights, or provenance. Ambiguity, insufficient evidence, and unsupported interpretation remain explicit states.

## Current implementation vs fixed target architecture

Repository documentation distinguishes the **current implementation** from the **fixed target architecture under implementation**.

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
Canonical processed records
  → Japanese-function projections
  → multi-lane front router
  → progressive retrieval of required indexes
  → hard gates
  → soft ranking
  → recovery zone only when required
  → bounded candidate lattice
  → whole-sentence Top-K decode
  → margin / evidence gate
  → existing MeaningGraph 2.3.0
  → TaskGraph
  → GraphGuard
```

The authoritative target architecture is [`docs/PARSER_ARCHITECTURE.md`](docs/PARSER_ARCHITECTURE.md).

**Documentation is not implementation evidence.** A target layer is not considered complete until its source, tests, full build/audit where applicable, performance evidence, regression evidence, and authorized runtime readback are closed.

## Architecture invariants

The target architecture keeps the following invariants:

- the original text remains authoritative and is never silently overwritten by normalization or recovery;
- unsupported meaning is not invented;
- ambiguity and unresolved states are preserved;
- runtime analysis remains deterministic and non-LLM;
- auxiliary evidence does not become semantic authority by association;
- Purpose/source roles are retrieval/permission hints, not final meaning authority;
- external actions fail closed when material uncertainty remains;
- rights and provenance are enforced at field/evidence level;
- semantic-hash compatibility is explicitly gated;
- logical responsibilities are not hard-wired one-to-one to physical databases.

## Japanese-function projections

The fixed design projects the canonical processed data into logical Japanese-language responsibility lanes instead of scanning one undifferentiated store for every request.

Primary lanes:

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

The latest fixed design references **9,852,513 canonical processed records**. The final projection rebuild and all-record audit for the new architecture must still be executed before that target runtime can be called complete.

## Front router and progressive retrieval

The deterministic front router chooses which logical lanes, facets, and indexes are relevant to the input. It does not decide final meaning.

A target Router Trace records selected lanes, skipped lanes, detected features, secondary facets, retrieval limits, recovery need, and router/projection versions.

Progressive retrieval means loading only the evidence needed to resolve the request and escalating only when necessary. It is an efficiency architecture, not a feature-reduction mechanism.

## Purpose routing boundary

Purpose/source routing may provide retrieval hints, role masks, consumer allow/deny information, permissions, provenance, ranking, and evidence metadata.

It must not:

- become the sole meaning classifier;
- replace Japanese-function lanes;
- create lexical meaning from auxiliary evidence;
- bypass field-level rights/provenance;
- turn unknown roles into implicit permission.

## Noisy and typo recovery

The target architecture does **not** build a giant database of possible typos.

Recovery is bounded and conditional:

```text
original input
→ safe normalization
→ exact/normal analysis
→ recovery only for unresolved/OOV/abnormal segmentation
→ bounded surface/reading/alias/morphology/split-merge candidates
→ deterministic recovery cost
→ candidate lattice
→ whole-sentence Top-K decode
→ grammar/syntax/sense/context/facet/evidence rerank
→ margin + evidence gate
→ resolved OR explicit ambiguous/unresolved result
```

Unknown or newly coined expressions are not automatically classified as typos. The original input remains available. If recovery creates or changes actionable semantics, external action fails closed unless the required safety evidence is satisfied.

## MeaningGraph, TaskGraph and GraphGuard

The target architecture reuses the existing `MeaningGraph` `2.3.0`, `TaskGraph`, and `GraphGuard` rather than rewriting them from scratch.

`MeaningGraph` remains the semantic authority. `TaskGraph` is derived downstream from interpreted meaning. `GraphGuard` remains the final deterministic safety boundary for `execution_mode="external_action"`.

DJPMCP itself does not perform external actions.

## semantic_hash compatibility

The current `MeaningGraph` semantic hash covers graph content other than the `semantic_hash` field itself. Adding default graph fields can therefore alter hashes for previously stable inputs.

Router Trace, Recovery Evidence, field-level rights, and related extensions must not be attached to the graph until a compatibility gate proves either:

1. the extension preserves the existing hashed semantic payload; or
2. an explicit graph/hash version migration is defined, tested, and released.

Unexpected hash drift is not accepted.

## MCP progressive output profiles

The target MCP transport supports:

```text
output_profile = compact | standard | full
Default = full
```

`output_profile` is transport-only and must not become part of the core semantic `AnalyzeRequest`.

- `full`: current complete `AnalyzeResponse`, backward-compatible default.
- `standard`: semantic/status/task/reading material while omitting heavy transport details where schema-compatible.
- `compact`: minimum decision material including status, safety, unresolved/ambiguity signals, propositions, and semantic identity/hash.

Profile selection must not change parser semantics, cache identity, or `semantic_hash`. The text summary remains backward compatible.

At the verified baseline, these profiles are **designed but not yet applied to VPS source**.

## Current MCP input contract

Until the profile extension is implemented, the current `analyze_japanese` input remains the existing `AnalyzeRequest`:

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

A successful current MCP response includes complete `AnalyzeResponse` structured content plus the compact text summary.

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

Development dependencies:

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

For production boundaries, see [`docs/PRODUCTION_HTTP_DEPLOYMENT.md`](docs/PRODUCTION_HTTP_DEPLOYMENT.md).

## Canonical data and runtime projections

The repository keeps source intake, canonical data, public distribution views, runtime projections, and compiled indexes as separate layers.

Conceptually:

```text
verified source
→ source adapter
→ schema / provenance / rights validation
→ review / decision ledger
→ canonical processed records
→ Japanese-function projection compiler
→ runtime bundles / indexes
```

The target architecture does not consider a new projection build complete until input/output/rejected/unresolved accounting, rights/provenance audit, deterministic hashes, and all-record audit are closed.

See:

- [`docs/UNIFIED_SEMANTIC_DATA_PIPELINE.md`](docs/UNIFIED_SEMANTIC_DATA_PIPELINE.md)
- [`docs/OPEN_DICTIONARY_SUPPLY_CHAIN.md`](docs/OPEN_DICTIONARY_SUPPLY_CHAIN.md)
- [`docs/LANGUAGE_DATA_RUNTIME.md`](docs/LANGUAGE_DATA_RUNTIME.md)
- [`docs/DIRECT_FINAL_RUNTIME_DEPLOYMENT.md`](docs/DIRECT_FINAL_RUNTIME_DEPLOYMENT.md)

## Logical runtime bundles

The initial logical bundle plan is:

- `router_core`
- `grammar_core`
- `lexical_semantic`
- `context_evidence`
- `recovery_index`

These are responsibility boundaries, not a requirement for five physical databases. Physical layout is benchmark-driven.

## Performance and validation

Existing narrower 10 ms / 50 ms contracts remain valid for their documented scopes unless explicitly migrated.

The fixed final acceptance target for the complete new architecture is a production-representative **p95 < 500 ms** benchmark, together with correctness, ambiguity retention, recovery safety, and bounded work.

The final architecture requires evidence for:

- MCP output-profile compatibility;
- semantic-hash compatibility;
- Router Trace;
- Recovery Interpretation Evidence;
- field-level rights/provenance;
- full canonical rebuild and all-record audit;
- clean/noisy/typo/broken-input regression;
- false-correction and ambiguity-retention metrics;
- external-action recovery safety;
- final performance;
- full regression;
- authorized runtime deployment/readback.

Process start, HTTP 200, successful build, a finished test runner, or CI green alone is not semantic completion evidence.

## Fixed implementation order

```text
M0-1 MCP compact / standard / full
→ targeted MCP tests
→ semantic_hash compatibility gate
→ Router Trace
→ Recovery Interpretation Evidence
→ Field-level Rights / Provenance
→ Japanese-function Projection Compiler
→ Front multi-lane Router
→ Recovery Index / Lattice / Top-K
→ Progressive Context Retrieval
→ 9.85M full build / audit
→ clean + noisy + typo + broken regression
→ false-correction / ambiguity-retention
→ final p95 < 500 ms
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
| MCP `compact/standard/full` | DESIGN FIXED / SOURCE NOT YET APPLIED at verified baseline |
| semantic-hash compatibility gate | NOT IMPLEMENTED |
| Router Trace | NOT IMPLEMENTED |
| Recovery Evidence / Index / Lattice / Top-K | NOT IMPLEMENTED |
| field-level rights/provenance extension | NOT IMPLEMENTED |
| Japanese-function projection compiler | NOT IMPLEMENTED |
| Front multi-lane router | NOT IMPLEMENTED |
| Progressive Context Retrieval | NOT IMPLEMENTED |
| final 9.85M rebuild/audit | NOT RUN |
| final robustness | NOT RUN |
| final p95 | NOT RUN |
| final full regression | NOT RUN |
| target-architecture runtime deployment | NOT DEPLOYED |

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

Until then, each scope is reported separately as `PASS`, `FAIL`, `PARTIAL`, `BLOCKED`, `UNKNOWN`, `NOT_RUN`, or `NOT_IMPLEMENTED`.