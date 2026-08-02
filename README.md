# Deterministic Japanese Parser MCP

A deterministic, non-generative MCP server for Japanese intent extraction, metaphor detection, reference resolution, and task decomposition.

## What it guarantees

- Original text is preserved.
- Normalized text is stored separately.
- Every extracted item includes an original-text span.
- Missing or ambiguous references are not silently completed.
- External actions are blocked when critical uncertainty remains.
- System dictionaries and user dictionaries are separated.

## Included initial data

- 151 curated metaphor / idiom entries
- 148 deterministic intent patterns across 21 intent types
- 29 task and workflow templates
- 20 canonical synonym groups
- 150 Gold Corpus cases

The bundled definitions are original project data. SudachiPy and SudachiDict are external dependencies and retain their own licenses.

## Install

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

## Validate immediately

```bash
python tools/validator.py
pytest
python scripts/test_harness.py
python scripts/benchmark.py
```

## Run as MCP server

```bash
djpmcp
```

## Direct Python call

```python
from deterministic_japanese_parser_mcp import ParserEngine, AnalyzeRequest

response = ParserEngine().analyze(AnalyzeRequest(
    original_text="今のUIは殺すな。APIだけ変更しろ。",
    execution_mode="external_action",
))
print(response.model_dump_json(indent=2))
```

## Dictionary structure

```text
dictionaries/
├── system/       # versioned project defaults
│   ├── metaphors/       # domain-sized JSON files
│   ├── rules/           # one YAML file per intent
│   ├── synonyms.yaml
│   └── task_templates.yaml
└── user/         # local overrides; empty by default
    ├── metaphor.json
    ├── rules.yaml
    ├── synonyms.yaml
    └── task_templates.yaml
```

## Improve from real logs now

The server records `UNSUPPORTED`, `AMBIGUOUS`, `INSUFFICIENT`, and `CONTRADICTORY` results as JSONL. The following commands create reviewable proposals; they never auto-merge into `system/`.

```bash
python tools/learner.py --log logs/parser.jsonl --out proposals/from_logs.yaml
python tools/expander.py --out proposals/synonym_expansion.yaml
python tools/gold_generator.py --log logs/parser.jsonl --out proposals/gold_candidates.json
python tools/validator.py
```

## Public contribution rule

Every dictionary change must include: source expression, deterministic interpretation, context/domain, a Gold Corpus case, and passing validation. Generated proposals are review data, not trusted system data.

## License

MIT. See `LICENSE` and `NOTICE.md`.
