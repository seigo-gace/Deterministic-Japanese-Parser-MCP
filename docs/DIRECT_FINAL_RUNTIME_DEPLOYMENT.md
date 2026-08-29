# Direct Final Runtime Deployment

The Drive-hosted direct-final runtime data is the practical deployment data path
for the completed MCP dictionary. It is separate from the historical 120k Open
Lexicon snapshot: the 120k snapshot is lexical identity only and must not be
treated as meaning-complete runtime data.

## Boundary

- Runtime remains non-AI and deterministic.
- The compiler does not call external dictionary or LLM APIs.
- `factory_used=false` is required and verified.
- Only source-provided `senses` become semantic runtime records.
- Rows without source-provided senses stay lexical-only; meanings are not
  generated or inherited from aliases.
- The existing runtime ABIs are used:
  - `compiled/open_lexicon`
  - `compiled/canonical_dictionary_runtime`

## Expected Input

Place these files in one local input directory:

- `manifest.json`
- `mcp-runtime-final-part-001.jsonl.gz` through
  `mcp-runtime-final-part-016.jsonl.gz`
- `mcp-runtime-support.jsonl.gz`

The manifest schema must be `djpmcp.direct-runtime-final.manifest.v1` and the
target must be `Deterministic-Japanese-Parser-MCP`.

The known completed Drive bundle from 2026-08-18 declares:

- Runtime entries: `9,852,513`
- Runtime source datasets: `55`
- Support-only datasets: `3`
- Final part count: `16`
- Missing required core fields: `0`
- Gzip integrity: `PASS`

## Compile

```bash
python tools/compile_direct_final_runtime.py \
  --manifest /path/to/direct-final/manifest.json \
  --input-root /path/to/direct-final \
  --system-root dictionaries/system \
  --work-root work/direct-final-runtime
```

The compiler validates file sizes, SHA-256 values, row counts, support pack
integrity, and manifest boundaries before writing runtime output.

## Verify

```bash
python -m pytest tests/test_direct_final_runtime_integration.py
python tools/validator.py --global-only
python scripts/semantic_quality_contract.py --check
python scripts/semantic_holdout_contract.py --check
python scripts/benchmark.py --check --rounds 100
python scripts/performance_contract.py --check --rounds 100 --stdio-rounds 50
```

For installed-wheel verification, ensure the compiled dictionary directory is
available through the package data or set:

```bash
export DJPMCP_SYSTEM_DICT_DIR=/absolute/path/to/dictionaries/system
```

## Deployment Decision

Do not deploy the checked-in 120k lexical snapshot as the completed semantic
runtime. Deploy only after the direct-final bundle has been compiled and the
resulting `compiled/open_lexicon`, `compiled/canonical_dictionary_runtime`, and
`compiled/direct_final_integration.json` have passed verification.
