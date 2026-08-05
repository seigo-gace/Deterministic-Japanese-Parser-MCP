# Context Data Expansion v3 — 5,000 Candidate Build Report

## Result

- Total candidate entries: **5,000**
- Normalized unique surfaces: **5,000**
- Rehydrated YAML files: **5,000**
- Validation errors: **0**
- Mock input: **false**
- Placeholder padding: **0**
- Known malformed construction count: **0**
- Review status: **all `needs-evidence`**
- Runtime promotion: **not allowed**

## Category counts

| Category | Count |
|---|---:|
| dialect | 400 |
| discourse | 400 |
| epistemic | 200 |
| honorific | 500 |
| media_community | 500 |
| metaphor | 500 |
| modality | 500 |
| onomatopoeia | 700 |
| reference | 300 |
| slang | 1000 |

## Provenance boundary

- Retained v2 / Web vocabulary / orthographic or Web-backed surface candidates: **2,638**
- Productive Japanese construction expansions: **2,362**

The productive constructions cover modality, honorifics, discourse management, metaphor framing, dialect constructions, reference/ellipsis, and evidentiality. They are candidate patterns, not claims that every complete phrase was independently attested on a separate webpage.

No source definitions or copyrighted example sentences were copied. Positive, negative, and boundary examples are constructed test scaffolding. Meaning, polarity, generation, community, regional scope, and current usage must be reviewed in the evidence stage.

## Canonical GitHub storage

The GitHub branch stores the complete 5,000-row compact inventory as nine Base64 parts plus a deterministic YAML rehydrator and dependency-free validator.

- Inventory XZ SHA-256: `2945cfb324df112001af3d1d72d8e529ba6ddb351419f9185b6e8f732f661db1`
- Inventory XZ bytes: `61404`
- Base64 parts: `9`
- Rehydrator: `data/generate_yaml_from_inventory.py`
- Validator: `data/validate_generated.py`
- Part ledger: `data/inventory_checksums.json`
- Instructions: `data/README.md` and `archive/REASSEMBLE.md`

A separately built local archive contains the same 5,000 YAML files:

- File: `context-expansion-v3-5000.tar.xz`
- SHA-256: `06d832a6ce5669f95b4a3f84ad157fce6761e283c030ef410c9c622360cd6406`
- Archive bytes: `478888`

The binary archive itself is not claimed to be stored in GitHub. GitHub reconstructs the YAML files from the canonical compact inventory.

## Validation gates

- [x] exactly 5,000 YAML files
- [x] exactly 5,000 normalized unique surfaces
- [x] exact category quotas
- [x] required schema fields
- [x] Positive / Negative / Boundary examples
- [x] source and license fields
- [x] all entries remain `needs-evidence`
- [x] mock/placeholder rejection
- [x] known malformed-construction rejection
- [x] no runtime dictionary change
