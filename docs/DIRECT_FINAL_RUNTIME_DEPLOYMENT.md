# Direct Final Runtime Deployment

Direct Final runtime data is the practical deployment data path for the
completed MCP dictionary. It is separate from the historical 120k Open Lexicon
snapshot: the 120k snapshot is lexical identity only and must not be treated as
meaning-complete runtime data.

The operational source of truth for deployable Direct Final data is GitHub:
GitHub Release assets are preferred for durable storage, GitHub Actions
artifacts are acceptable for short-lived handoff, and an explicit branch bundle
may be used when the repository is intentionally carrying the data. Drive and
Notion are not runtime sources of truth.

## Boundary

- Runtime remains non-AI and deterministic.
- The compiler does not call external dictionary, Drive, Notion, or LLM APIs.
- `factory_used=false` is required and verified.
- Only source-provided `senses` become semantic runtime records.
- Rows without source-provided senses stay lexical-only; meanings are not
  generated or inherited from aliases.
- Notion is not a runtime data source and is not accepted for practical
  deployment.
- Drive is only a temporary or emergency staging location before data is moved
  into GitHub-managed release/artifact storage.
- The existing runtime ABIs are used:
  - `compiled/open_lexicon`
  - `compiled/canonical_dictionary_runtime`

## Expected Input

Place the Direct Final files in one local input directory or publish the same
files as GitHub-managed release/artifact assets:

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

Do not copy private staging identifiers, Drive folder IDs, file IDs, or complete
private manifest metadata into public PR text or repository documentation.

## GitHub-Managed Deployment

Preferred durable path: publish the Direct Final bundle as GitHub Release assets
and run `.github/workflows/direct-final-runtime-from-release.yml`.

Required workflow inputs:

```text
release-tag = <GitHub Release tag containing the Direct Final bundle>
asset-pattern = <release asset glob for final parts>
expected-records = <manifest expected runtime count>
bundle-root = <optional extracted bundle directory>
```

Short-lived handoff path: use `.github/workflows/direct-final-runtime.yml` with a
GitHub Actions artifact that already contains the Direct Final bundle. This is
useful for a controlled CI handoff, but artifact retention is limited by GitHub
Actions retention settings.

Required workflow inputs:

```text
artifact-run-id = <GitHub Actions run ID containing the Direct Final bundle>
artifact-name = <artifact name containing manifest.json and final parts>
expected-records = <manifest expected runtime count>
bundle-root = <optional artifact directory>
```

Both GitHub deployment workflows perform these gates before release evidence is
accepted:

- locate `manifest.json` and all manifest-declared final/support files
- validate schema, target, `factory_used=false`, gzip integrity, missing-core
  field count, final part count, SHA-256 values, and expected runtime record
  count
- compile the Direct Final bundle into existing runtime ABIs
- run `scripts/direct_final_deployment_contract.py --require-direct-final`
- run direct-final integration, deployment contract, semantic runtime tests,
  global validator, semantic quality, semantic holdout, Astera latency, and
  `compileall`
- build the wheel and verify the installed wheel outside the repository

## Emergency Drive Import

`.github/workflows/direct-final-runtime-from-drive.yml` is not a deployment path.
It is an emergency/manual importer for cases where the Direct Final bundle exists
only in a temporary Drive folder and must be staged into GitHub-managed storage.

The Drive importer is `workflow_dispatch` only, uses readonly Drive access, and
does not compile, build, verify the runtime, or upload deployable runtime release
evidence. It may upload the staged source bundle only when
`upload-source-bundle=true` is explicitly provided. Keep that input `false`
unless exporting the staged source bundle into GitHub artifacts has been
approved.

## Local Compile

Repo-native preparation from GitHub Release (default output under `work/` so the
checked-in 120k baseline under `dictionaries/system` is not overwritten):

```bash
python tools/prepare_direct_final_runtime.py \
  --release-tag <GitHub Release tag> \
  --expected-records <manifest full_json_records_validated>
export DJPMCP_SYSTEM_DICT_DIR="$(python -c 'import json,sys; print(json.load(sys.stdin)["DJPMCP_SYSTEM_DICT_DIR"]')" \
  < <(python tools/prepare_direct_final_runtime.py \
        --release-tag <GitHub Release tag> \
        --expected-records <manifest full_json_records_validated>)
```

Low-level compile when the Direct Final bundle is already on disk:

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
runtime. Deploy only after the GitHub-managed Direct Final bundle has been
compiled and the resulting `compiled/open_lexicon`,
`compiled/canonical_dictionary_runtime`, and
`compiled/direct_final_integration.json` have passed verification.

Do not add branch `push` or PR triggers that automatically export private staged
source data into GitHub artifacts unless that specific export destination has
been explicitly approved. The safe default is GitHub-managed Release assets or
explicit artifact handoff, with Drive limited to temporary emergency import.
