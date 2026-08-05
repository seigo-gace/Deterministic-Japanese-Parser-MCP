# Dictionaries

`system/` contains versioned project defaults. `user/` contains local overrides.

## Structure

```text
dictionaries/
├── system/
│   ├── metaphors/                     # Project-reviewed metaphor and pragmatic entries
│   ├── rules/                         # Deterministic intent and constraint rules
│   ├── synonyms.yaml
│   ├── synonyms.d/
│   ├── task_templates.yaml
│   ├── task_templates.d/
│   ├── language_features.d/
│   ├── lexicon.d/                     # Auditable 120,000-record source snapshot
│   │   └── cc-by-sa/
│   │       ├── release-...-0001.jsonl.gz
│   │       ├── ...
│   │       └── release-...-0012.jsonl.gz
│   └── compiled/
│       ├── language_features.d/
│       └── open_lexicon/              # Runtime form generated from the source snapshot
│           ├── manifest.json
│           ├── indexes/
│           └── records/
│               ├── records-0000.jsonl.gz
│               ├── ...
│               └── records-0011.jsonl.gz
├── sources/                            # Provenance ledger
└── user/
    ├── metaphor.json
    ├── rules.yaml
    ├── synonyms.yaml
    └── task_templates.yaml
```

## Why the 120,000 records are split

The records are split only as files. They are not separate dictionaries.

- The repository source snapshot is divided into **12 files of 10,000 records** so it can be audited, rebuilt, and compared deterministically.
- The runtime copy is also divided into **12 compact record files**, with indexes that map every surface, reading, and record ID to the correct record.
- Before the server reports ready, the runtime loads all 12 compact files and verifies that the total is exactly **120,000**.
- Requests use the complete index and the complete preloaded record set. No shard operates independently.

In other words, this is one dictionary stored in manageable volumes, similar to one reference work divided into several books with a shared index.

The source snapshot remains in the repository for provenance and reproducible rebuilding. Release wheels contain only the compiled runtime copy, so users do not receive two duplicate copies of the same 120,000 records.

## Current volume

| Data | Count |
|---|---:|
| Metaphor, idiom, and pragmatic expressions | **452** |
| Deterministic intent rules | **339** |
| Intent types | **21** |
| Canonical synonym groups | **100** |
| Task and workflow templates | **63** |
| Workflows | **42** |
| Gold validation cases | **649** |
| Open lexical records | **120,000** |
| Unique lemmas | **119,092** |
| Exact surfaces | **154,921** |
| Readings | **126,936** |
| Ambiguous same-surface entries | **1,711** |

## Promotion and safety rules

- Generated proposals never merge automatically.
- Every promoted record keeps its source dataset, version, license, source ID, and source hash.
- Open lexical records provide lexical identity candidates only.
- Readings are not promoted into orthographic aliases.
- Imported entries are not automatically promoted into reviewed synonyms, semantic senses, intents, tasks, pragmatic meanings, or external actions.
- Same-surface ambiguity is preserved instead of being collapsed.
- Unresolved candidates remain unresolved.
- System dictionaries and user overrides remain separate.
- Manifest counts, full index coverage, deterministic rebuilds, offline installation, regression tests, and performance gates must pass before merge.

## Validation

```bash
python tools/lexicon_validator.py
python tools/validator.py
pytest
python scripts/performance_contract.py --check --max-ready-ms 10
python scripts/astera_latency_contract.py --check --target-ms 10 --hard-ms 50
```

The dedicated `Compile 120k Open Lexicon` workflow rebuilds all 120,000 records in a temporary directory, compares the result with the checked-in runtime assets, proves that all 12 runtime shards are loaded as one dictionary, and never writes back to a branch.
