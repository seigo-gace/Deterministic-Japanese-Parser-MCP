# Context Data v3 canonical data

This directory is the GitHub-only canonical representation of the 5,000 candidate entries.

## Contents

- `context-v3-surface-inventory.json.xz.part00.b64` … `part08.b64`: 5,000 compact candidate rows, split into nine fixed Base64 parts.
- `inventory_checksums.json`: size, SHA-256, and Git blob SHA ledger for every part.
- `generate_yaml_from_inventory.py`: verifies the inventory and deterministically emits one YAML file per entry.
- `validate_generated.py`: dependency-free structural validation of the emitted YAML collection.

Each compact row contains:

```text
[entry_id, category, surface, reading, variants, source_urls]
```

The generator adds the required collection-stage fields without asserting reviewed semantics. Every entry remains `review_status: needs-evidence`.

## Generate and validate

```bash
python research/context_collection/expansion_v3/data/generate_yaml_from_inventory.py \
  --data-dir research/context_collection/expansion_v3/data \
  --output research/context_collection/expansion_v3/generated

python research/context_collection/expansion_v3/data/validate_generated.py \
  research/context_collection/expansion_v3/generated
```

Expected result:

```json
{
  "ok": true,
  "yaml_files": 5000,
  "unique_surfaces": 5000,
  "errors": []
}
```

## Boundary

- This completes the **candidate-discovery volume gate**, not semantic approval.
- 2,638 entries are retained v2/Web/orthographic candidates.
- 2,362 entries are productive Japanese construction expansions.
- Productive patterns are candidate constructions; they are not represented as independently attested complete phrases.
- Meaning, polarity, intensity, generation, community, regional scope, license, and current usage require evidence review.
- No runtime dictionary or parser behavior is changed by this collection.
