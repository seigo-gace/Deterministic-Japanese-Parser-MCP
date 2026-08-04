# Context Data v3 — GitHub-only reconstruction

The canonical GitHub representation is the validated compact inventory plus a deterministic YAML rehydrator. This avoids pretending that a partially uploaded binary archive is complete.

## Recreate all 5,000 YAML files

```bash
cd research/context_collection/expansion_v3/data
python generate_yaml_from_inventory.py \
  --data-dir . \
  --output ../generated
python validate_generated.py ../generated
```

The generator performs these gates before writing files:

- exactly 9 Base64 inventory parts
- decoded XZ SHA-256: `2945cfb324df112001af3d1d72d8e529ba6ddb351419f9185b6e8f732f661db1`
- exactly 5,000 inventory rows
- exactly 5,000 globally unique normalized surfaces
- exact category quotas

The validator then confirms 5,000 YAML files, required schema fields, category quotas, global uniqueness, `needs-evidence`, and zero mock/placeholder padding.

## Independently built archive

A full local artifact containing the same 5,000 YAML files was built and validated:

- file: `context-expansion-v3-5000.tar.xz`
- SHA-256: `06d832a6ce5669f95b4a3f84ad157fce6761e283c030ef410c9c622360cd6406`
- bytes: `478888`
- YAML files: `5000`

The binary archive itself is not claimed to be stored in this GitHub directory. GitHub reconstruction uses the inventory and scripts above.
