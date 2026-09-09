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
- Notion is not a runtime data source and is not accepted for practical
  deployment.
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

## Verified Drive Bundle

As of 2026-09-09, the direct-final bundle is located in Google Drive:

- Folder: `MCP完成版データ_2026-08-18`
- Folder ID: `13VJ9E5fbVHIJZWddiOGWAw_l7rQJmIES`
- Manifest file ID: `1DBhSxQD8nZE-QZ-roCviC1v7b8CTkr5r`
- Manifest modified time: `2026-08-17T17:16:20.327Z`

Folder listing was verified to contain:

- `manifest.json`
- `mcp-runtime-final-part-001.jsonl.gz` through
  `mcp-runtime-final-part-016.jsonl.gz`
- `mcp-runtime-support.jsonl.gz`
- `README.txt`

The Drive folder is shared and the current connected user can share it. The
observed folder permissions on 2026-09-09 were owner/writer user permissions;
no service-account reader was visible from the available metadata. Before a
GitHub Actions deployment run, share the folder with the service account whose
JSON is stored in the `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON` repository secret.

## GitHub Actions Deployment

Use `.github/workflows/direct-final-runtime-from-drive.yml` for deployment from
Drive. It is intentionally `workflow_dispatch` only so private Drive data is not
automatically exported to GitHub artifacts by ordinary PR or push activity.

Required repository secret:

```text
GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON
```

Required workflow inputs:

```text
drive-folder-id = 13VJ9E5fbVHIJZWddiOGWAw_l7rQJmIES
artifact-name = mcp-runtime-direct-final-v1
expected-records = 9852513
```

The workflow performs these gates before upload/release evidence:

- authenticates with Google Drive readonly scope
- lists the Drive folder and requires all manifest-declared files
- validates Drive-reported size and SHA-256 for each final part and support pack
- validates schema, target, `factory_used=false`, gzip integrity, missing-core
  field count, final part count, and expected runtime record count
- compiles the direct-final bundle into existing runtime ABIs
- runs `scripts/direct_final_deployment_contract.py --require-direct-final`
- runs direct-final integration, deployment contract, semantic runtime tests,
  global validator, semantic quality, semantic holdout, Astera latency, and
  `compileall`
- builds the wheel and verifies the installed wheel outside the repository

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

## Current PR Evidence

At PR head `dc0fde8cc7465caa5c56530144dcafef9e811527`, all PR-triggered checks
completed successfully on 2026-09-09. Release Readiness produced artifact
`deterministic-japanese-parser-offline-release`, artifact id `10119258235`,
digest `sha256:4b32f00863988dc4d7e150faf03f8321672589b8e0230c61b8fd7c7ae87a0d59`,
expiring `2026-10-09T18:36:55Z`.

That artifact is the offline release for the checked-in compatibility snapshot.
It is useful release evidence, but it is not the completed 9,852,513-record
Direct Final semantic runtime.

## Deployment Decision

Do not deploy the checked-in 120k lexical snapshot as the completed semantic
runtime. Deploy only after the direct-final bundle has been compiled and the
resulting `compiled/open_lexicon`, `compiled/canonical_dictionary_runtime`, and
`compiled/direct_final_integration.json` have passed verification.

Do not add branch `push` or PR triggers that automatically export the private
Drive bundle into GitHub artifacts unless that specific data export destination
has been explicitly approved. The safe default is manual dispatch with the
service account secret and folder sharing prepared first.
