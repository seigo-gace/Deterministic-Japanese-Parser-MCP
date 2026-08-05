# Deterministic Japanese Parser MCP

<p align="center">
  <strong>A deterministic MCP server that structures Japanese meaning, conditions, prohibitions, exceptions, references, and execution safety without generative AI</strong>
</p>

<p align="center">
  <a href="README.md">Japanese</a> ｜ <strong>English</strong>
</p>

<p align="center">
  <a href="https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP/actions/workflows/ci.yml/badge.svg"></a>
</p>

| Item | Value |
|---|---|
| Runtime model | Non-AI, non-generative, deterministic |
| Supported Python | Python 3.10+ |
| Interfaces | MCP stdio and Python API |
| Program license | MIT |
| External AI at runtime | None |
| External dictionary access at runtime | None |

[Install](#installation) ｜ [Usage](#usage) ｜ [Validation](#validation) ｜ [Join validation](VALIDATION.md) ｜ [Report a confirmed bug](https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP/issues/new?template=bug_report.yml) ｜ [Validation and questions](https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP/discussions)

---

## Overview

**Deterministic Japanese Parser MCP** transforms Japanese input into a typed **Meaning Graph** instead of reducing it to a flat intent list.

It structures:

- who requests what and against which target;
- conditions, exceptions, prohibitions, preservation, priority, sequence, and dependencies;
- quotation, questions, hypotheses, hearsay, corrections, and withdrawal;
- omitted targets and unresolved references;
- actions that may proceed and actions that must remain blocked.

The runtime does not call a large language model or external AI. It combines version-locked dictionaries, morphological information, precompiled rule indexes, deterministic grammar processing, typed scope resolution, conversation context, contradiction detection, a Task Graph, and an External Action Guard.

The server does not generate a natural-language answer. It returns a validated structure for downstream systems that need to handle Japanese instructions and constraints safely.

## Main response fields

- `meaning_graph.entities`: people, objects, organizations, and other entities
- `meaning_graph.clauses`: clause structure
- `meaning_graph.propositions`: requests, judgments, states, and relations
- `meaning_graph.scope_edges`: scope of negation, conditions, quotation, and questions
- `meaning_graph.unresolved`: unresolved meaning, reference, or omission
- `task_graph.tasks`: candidate actions
- `task_graph.constraints`: preservation, prohibition, conditions, exceptions, and protected targets
- `execution_allowed`: whether an external action may proceed
- `blocked_reasons`: reasons for blocking

The same input, context, dictionary version, and rule version produce the same Semantic Hash.

## Safety model

The following are not promoted directly into executable actions:

- commands inside quotations;
- questions such as “Should this be deleted?”;
- hypotheses such as “Delete it if it is unnecessary”;
- reported speech such as “I was told to delete it”;
- instructions with unresolved demonstratives;
- contradictory preservation and modification requirements;
- requests whose critical meaning cannot be resolved before the deadline.

When meaning, target, scope, or contradiction remains unresolved, the runtime fails closed instead of inventing an answer.

## Current promoted data

| Data | Count |
|---|---:|
| Metaphor, idiom, and pragmatic expressions | **452** |
| Deterministic intent rules | **339** |
| Intent types | **21** |
| Canonical synonym groups | **100** |
| Task and workflow templates | **63** |
| Workflows | **42** |
| Gold validation cases | **649** |

Release artifacts contain an offline snapshot of **120,000 JMdict records** transformed and audited for lexical identity lookup.

These records provide lexical identity data. They are not an automatic claim that every imported word has fully reviewed semantics, pragmatics, or executable intent.

## Current 120k lexicon values

| Validation gate | Current result |
|---|---:|
| Source snapshot rebuilt into runtime data | **120,000 / 120,000** |
| Runtime record-locator coverage | **120,000 / 120,000** |
| Exact surfaces | **154,921** |
| Readings | **126,936** |
| Surfaces with multiple records | **1,711, all candidates retained** |
| Runtime shards loaded | **12 / 12** |
| File differences after deterministic rebuild | **0** |
| Detected connection or integrity errors | **0** |

See [`docs/OPEN_LEXICON_ACCURACY.md`](docs/OPEN_LEXICON_ACCURACY.md) for the full contract.

## Why the 120,000 records are split

The repository stores the records in twelve files of 10,000 records each. They are not used as twelve independent dictionaries.

```text
12 auditable source files
  ↓ deterministic full rebuild
shared search indexes + 12 compact runtime files
  ↓ all 12 files loaded before readiness
one 120,000-record dictionary used by ParserEngine
```

Shared indexes connect surfaces, readings, and record IDs to the correct records. Readiness fails unless all twelve runtime files load and the total is exactly 120,000.

The repository retains the source snapshot for provenance and reproducible rebuilding. Release wheels include only the compiled runtime copy, avoiding a duplicate second copy of the same 120,000 records.

## Open dictionary supply chain

Open machine-readable resources are processed through the following gates:

```text
Official open data
  ↓
Version-pinned download and hash manifest
  ↓
Source-specific importer
  ↓
Common lexicon schema
  ↓
Duplicate, collision, and polysemy review
  ↓
Positive, negative, and boundary examples
  ↓
Human review of meaning, provenance, and license
  ↓
Regression, safety, performance, and offline validation
  ↓
Promotion of approved records only
```

Primary supported sources include:

- Japanese Wiktionary
- Wikidata Lexemes
- JMdict
- SudachiDict source data

Candidate data is never promoted automatically. Meaning, usage context, provenance, license, collisions, and safety must be reviewed first.

Details:

- [`docs/OPEN_DICTIONARY_SUPPLY_CHAIN.md`](docs/OPEN_DICTIONARY_SUPPLY_CHAIN.md)
- [`tools/README.md`](tools/README.md)
- [`dictionaries/README.md`](dictionaries/README.md)

## Installation

### Linux and macOS

```bash
git clone https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP.git
cd Deterministic-Japanese-Parser-MCP
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
djpmcp
```

### Windows PowerShell

```powershell
git clone https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP.git
cd Deterministic-Japanese-Parser-MCP
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
djpmcp
```

## Usage

### Python API

```python
from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine

response = ParserEngine().analyze(
    AnalyzeRequest(
        original_text="UIは維持する。APIだけ変更しろ。",
        execution_mode="external_action",
        deadline_ms=50,
    )
)

print(response.meaning_graph)
print(response.task_graph)
print(response.execution_allowed)
print(response.blocked_reasons)
```

### Processing flow

```text
Input
  ↓
Original-text preservation, normalization, and span mapping
  ↓
Morphology
  ↓
Rule, metaphor, and pragmatic candidates
  ↓
Deterministic grammar processing
  ↓
Meaning Graph
  ↓
Scope, reference, and contradiction validation
  ↓
Task Graph and constraints
  ↓
External-action allow or block decision
  ↓
Schema-validated response
```

## Validation

```bash
python tools/lexicon_validator.py
python tools/validator.py
pytest
python scripts/benchmark.py --check
python scripts/performance_contract.py --check --max-ready-ms 10
python scripts/astera_latency_contract.py --check --target-ms 10 --hard-ms 50
python -m compileall -q src tools scripts tests
```

Continuous validation covers:

- Python 3.10 and 3.12;
- dictionary and Gold data integrity;
- Meaning Graph and Task Graph behavior;
- quotation, questions, negation, hypotheses, and reference safety;
- complete source-snapshot to runtime-data reconstruction for all 120,000 records;
- unified loading of all twelve runtime shards;
- exact lookup, ambiguity retention, and complete index coverage;
- MCP stdio end-to-end behavior;
- offline installation;
- 20x dictionary-scale performance;
- the normal 10 ms target and absolute 50 ms limit.

## Community validation

You can contribute without writing code.

- review Japanese interpretation in five minutes;
- report suspicious or unnatural results;
- validate Windows, macOS, Linux, and MCP clients;
- review dialect, slang, metaphor, idiom, and pragmatic expressions;
- verify provenance, reading, meaning, region, generation, community, and license data for the 5,000 context candidates.

See [`VALIDATION.md`](VALIDATION.md) for participation rules.

### Discussions

Use Discussions for:

- validation participation and results;
- uncertain parser findings;
- Japanese-language review;
- installation and environment checks;
- candidate evidence review;
- questions and early improvement ideas.

[Open Discussions](https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP/discussions)

### Issues

Issues are reserved for **confirmed, reproducible bugs and regressions that require a fix**.

Questions, unverified suspicions, validation participation, and early ideas belong in Discussions.

[Report a confirmed bug](https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP/issues/new?template=bug_report.yml)

Do not disclose vulnerability details in a public Issue or Discussion. Follow [`SECURITY.md`](SECURITY.md).

## Performance contract

| Boundary | Contract |
|---|---:|
| Optimized resident-kernel goal | 5 ms or less |
| Normal call-through target | p95 at 10 ms or less |
| Absolute hard limit | 50 ms or less |
| Unresolved at the hard deadline | Return `TIMEOUT` and block external action |

The measured boundary includes persistent stdio transport, response decoding, output-schema validation, and delivery of the complete Meaning Graph, Task Graph, and Guard result.

## Scope and limitations

This project does not claim human-level understanding of arbitrary Japanese.

Irony, broad unstated world knowledge, complex ellipsis, long multi-paragraph discourse, and expressions that depend heavily on region, generation, or community are returned as unresolved when the fixed dictionaries and rules cannot provide explainable evidence.

The 120k lexicon contract verifies lexical identity accuracy. It does not guarantee complete semantic understanding of all 120,000 records.

## Documentation

- [`docs/README.md`](docs/README.md): public documentation index
- [`VALIDATION.md`](VALIDATION.md): community validation participation
- [`SUPPORT.md`](SUPPORT.md): routing for questions, bugs, and security reports
- [`CONTRIBUTING.md`](CONTRIBUTING.md): code, dictionary, and validation-data contribution requirements
- [`docs/SEMANTIC_QUALITY_CONTRACT.md`](docs/SEMANTIC_QUALITY_CONTRACT.md): semantic quality contract
- [`docs/OPEN_LEXICON_ACCURACY.md`](docs/OPEN_LEXICON_ACCURACY.md): 120k lexicon accuracy contract
- [`docs/OPEN_DICTIONARY_SUPPLY_CHAIN.md`](docs/OPEN_DICTIONARY_SUPPLY_CHAIN.md): dictionary supply-chain design
- [`docs/PUBLIC_RELEASE_CHECKLIST.md`](docs/PUBLIC_RELEASE_CHECKLIST.md): mandatory public release gates
- [`CHANGELOG.md`](CHANGELOG.md): change history

<!-- project-control-en:start -->
## Ownership, governance, and brand

**Created, designed, developed, and maintained by Seigo Kato ([`@seigo-gace`](https://github.com/seigo-gace)).**

Under [`GOVERNANCE.md`](GOVERNANCE.md), the Project Owner retains final authority over the official repository, architecture, releases, contribution acceptance, and permission to use names, logos, and other Project Marks.

Program code may be used, modified, and redistributed under the MIT License. The MIT License does not authorize modified forks, products, or services to present themselves as official through project names, logos, or branding. See [`TRADEMARK.md`](TRADEMARK.md).

External contributions require DCO sign-off. Substantive code, dictionary, Gold data, design, release, security, or governance changes require a Project-Owner-accepted [`CONTRIBUTOR_LICENSE_AGREEMENT.md`](CONTRIBUTOR_LICENSE_AGREEMENT.md) before merge.
<!-- project-control-en:end -->

## License

Program code is licensed under MIT. See [`LICENSE`](LICENSE) and [`NOTICE.md`](NOTICE.md).

Promoted external dictionary data remains governed by the source licenses recorded on each record and in the provenance manifests.
