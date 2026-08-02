# Contributing

Contributions are welcome for parser rules, metaphor and idiom entries, task templates, regression cases, documentation, and implementation fixes.

## Before changing a dictionary

A system dictionary entry must include:

- the exact Japanese expression or pattern;
- a deterministic interpretation or intent type;
- context and domain constraints;
- aliases only when they have the same meaning under the same constraints;
- at least one Gold Corpus case that proves the intended behavior;
- no copied third-party corpus sentence or proprietary dictionary definition.

Generated proposals are review material. They must never be merged automatically into `dictionaries/system/`.

## Validate a change

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
python tools/validator.py
pytest
python -m compileall -q src tools scripts tests
```

All commands must pass before a pull request is opened.

## Dictionary locations

- `dictionaries/system/`: versioned project defaults reviewed with regression cases.
- `dictionaries/user/`: local overrides and private customization; empty by default.
- `proposals/`: generated candidates that have not been trusted or merged.

## Pull request requirements

Describe:

1. the unsupported or incorrect input;
2. the deterministic rule or dictionary change;
3. the added regression case;
4. the validator and pytest results;
5. any compatibility or security impact.

Keep unrelated changes out of the same pull request.
