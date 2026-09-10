# Direct Final Runtime Deployment

The direct-final runtime data is the practical deployment data path for the
completed MCP dictionary. It is separate from the historical 120k Open Lexicon
snapshot: the 120k snapshot is lexical identity only and must not be treated as
meaning-complete runtime data.

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

Place the direct-final files in one local input directory:

- `manifest.json`
- `mcp-runtime-final-part-001.jsonl.gz` through the manifest-declared final part
  count
- `mcp-runtime-support.jsonl.gz`

The manifest schema must be `djpmcp.direct-runtime-final.manifest.v1` and the
target must be `Deterministic-Japanese-Parser-MCP`.

The manifest is the authority for:

- runtime record count
- source dataset count
- support-only dataset count
- final part count
- per-file size and SHA-256 values
- gzip integrity status
- missing required core field count

Do not copy private source identifiers, Drive folder IDs, file IDs, or complete
manifest metadata into public PR text or repository documentation.

## Private Source Handling

The direct-final source bundle is stored outside the public repository. Its
location and manifest details must be handled as private deployment
configuration, not as public project metadata.

Before a GitHub Actions deployment run:

- create or verify the `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON` repository secret
- share the private source folder with that service account
- keep Drive access readonly for the deployment job
- pass the source folder and expected runtime count through workflow inputs or
  repository/environment configuration

## GitHub Actions Deployment

Use `.github/workflows/direct-final-runtime-from-drive.yml` for deployment from
private Drive-backed source data. It is intentionally `workflow_dispatch` only so
private source data is not automatically exported to GitHub artifacts by ordinary
PR or push activity.

Required repository secret:

```text
GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON
```

Required workflow inputs:

```text
drive-folder-id = <private source folder id>
expected-records = <manifest expected runtime count>
artifact-name = <release artifact name>
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

## PR Evidence

For the current PR head, require all PR-triggered workflows to complete
successfully before merge or deployment promotion. The required evidence is:

- CI on supported Python versions
- Release Readiness, including offline rebuild, index audit, wheelhouse/project
  wheel build, immutable manifest, install from wheelhouse, installed-wheel
  verification outside repo, offline deployment gates, semantic/holdout gates,
  runtime performance gates, and evidence hashing/upload
- Dictionary Data Pipeline and factory/boundary workflows used by the PR

The Release Readiness artifact is the offline release for the checked-in
compatibility snapshot. It is useful release evidence, but it is not the
completed Direct Final semantic runtime.

## Deployment Decision

Do not deploy the checked-in 120k lexical snapshot as the completed semantic
runtime. Deploy only after the direct-final bundle has been compiled and the
resulting `compiled/open_lexicon`, `compiled/canonical_dictionary_runtime`, and
`compiled/direct_final_integration.json` have passed verification.

Do not add branch `push` or PR triggers that automatically export the private
source bundle into GitHub artifacts unless that specific data export destination
has been explicitly approved. The safe default is manual dispatch with the
service account secret and folder sharing prepared first.
