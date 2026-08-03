# Dictionaries

`system/` contains the versioned defaults distributed by the project. `user/` contains local overrides and starts empty.

```text
dictionaries/
├── system/
│   ├── metaphors/
│   │   ├── 01_operations_security.json
│   │   ├── 02_development_change.json
│   │   ├── 03_quality_validation.json
│   │   ├── 04_project_execution.json
│   │   ├── 05_scope_governance.json
│   │   ├── 06_risk_decision.json
│   │   ├── 07_analysis_problem_solving.json
│   │   ├── 08_communication_organization.json
│   │   ├── 09_system_information.json
│   │   ├── 10_process_workflow.json
│   │   ├── 11_control_reversibility.json
│   │   ├── 12_general.json
│   │   ├── 13_everyday_instruction.json
│   │   ├── 14_business_communication.json
│   │   ├── 15_development_operations.json
│   │   ├── 16_document_analysis.json
│   │   └── manifest.json
│   ├── rules/
│   │   ├── one YAML file per original intent type
│   │   └── common_usage_expansion.yaml
│   ├── synonyms.yaml
│   └── task_templates.yaml
└── user/
    ├── metaphor.json
    ├── rules.yaml
    ├── synonyms.yaml
    └── task_templates.yaml
```

## Current volume

- Metaphor / idiomatic expressions: **200**
- Deterministic intent patterns: **213**
- Intent types: **21**
- Canonical synonym groups: **40**
- Task / workflow templates: **39**
- Workflows: **18**
- Gold Corpus cases: **271**

## Research and adoption policy

Dictionary expansion starts with a broad candidate list. Candidates are reviewed for actual or likely use, meaning, speech intent, domain, literal-use collision, existing-entry overlap, and ability to create a natural Gold case.

Usage review may refer to:

- NINJAL BCCWJ frequency and usage resources
- NINJAL CEJC everyday-conversation vocabulary and discourse resources
- NINJAL corpus portal and Japanese web-corpus resources
- official GitHub, Digital Agency, and Microsoft technical documentation

External dictionary definitions and corpus passages are not copied. `interpretation` values are project-authored descriptions derived from the intended runtime behavior.

The full August 2026 candidate review, accepted entries, held entries, rejected entries, and reasons are recorded in [`docs/DICTIONARY_EXPANSION_2026-08.md`](../docs/DICTIONARY_EXPANSION_2026-08.md).

## Mandatory rules

- System entries are project-authored and versioned.
- Generated proposals never merge automatically.
- A metaphor surface or alias may belong to only one canonical metaphor entry.
- Short or highly polysemous metaphor surfaces require `context_policy: required_any` unless a specific reason is documented.
- Synonym surfaces may belong to multiple canonical groups; the Canonicalizer preserves the candidate set instead of hiding the collision.
- Every new metaphor expression requires an interpretation, context, domain, version, and Gold Corpus case.
- Every new intent rule must compile, contain an indexable mandatory literal, and fire in at least one Gold Corpus case.
- Every workflow must use contiguous ordered steps and include preparation, execution, verification, and recording where applicable.
- Manifest counts, dictionary counts, Gold coverage, indexed/exhaustive parity, latency, and offline installation must pass before merge.

## Validation

```bash
python tools/validator.py
pytest
python scripts/performance_contract.py --check --max-ready-ms 10
python scripts/astera_latency_contract.py --check --target-ms 10 --hard-ms 50
```
