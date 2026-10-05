# TGserver ZERO / GitHub Development Evidence

## Purpose

This project uses two separate evidence paths:

- Source / Test / Build / Verify evidence: this repository's GitHub Actions.
- Runtime / Server log evidence: the central TGserver ZERO reader in `seigo-gace/TGserver`.

The goal is that ChatGPT can retrieve development evidence directly without asking Master to copy routine test or runtime logs from a terminal.

## Development Probe

Workflow:

- `.github/workflows/dev-probe.yml`

Request contract:

- Issue title starts with `[DEV-PROBE]`.
- The requesting GitHub user must equal the repository owner.
- The Issue body is an execution request only.
- No Issue field is interpreted as a shell command, script path, URL, deployment target, secret, or server operation.

The workflow command set is fixed in repository source. It reuses the same canonical verification gates as `.github/workflows/ci.yml` on Python 3.10 and 3.12:

1. `scripts/preflight.py`
2. `tools/lexicon_validator.py`
3. `tools/validator.py`
4. `scripts/semantic_quality_contract.py --check`
5. `scripts/semantic_holdout_contract.py --check`
6. full `pytest`
7. `scripts/benchmark.py --check --rounds 50`
8. `scripts/performance_contract.py --check ...`
9. `scripts/astera_latency_contract.py --check ...`
10. `compileall`

The workflow uploads the generated `reports/` directory as three-day GitHub Actions artifacts. ChatGPT can read the job log and artifacts directly through GitHub.

Branch self-test run `37183892515` executed the canonical probe on Python 3.10 and 3.12 and both jobs succeeded. ChatGPT directly read the Python 3.12 job log and downloaded artifact `11295574923`; the artifact reports pytest `553` tests with `0` failures, `0` errors and `2` skips, semantic quality `167/167`, and independent semantic holdout `130/130`.

The temporary branch `push` trigger used only for pre-merge self-test is removed after this evidence is recorded. The final request path is the owner-only `[DEV-PROBE]` Issue trigger. Owner-Issue execution on the default branch remains a separate post-merge evidence state and must not be claimed before merge.

## TGserver ZERO runtime log path

DJPMCP is registered in TGserver ZERO's current repository map as:

- Repository: `seigo-gace/Deterministic-Japanese-Parser-MCP`
- Stream: `default`
- Project ID: `P006`

Project ID is not supplied by this repository to the reader and must not be guessed from Issue input. The central TGserver ZERO repository owns the mapping.

Runtime search flow:

```text
ChatGPT
  -> [TGZERO] Issue in seigo-gace/TGserver
  -> TGserver ZERO central reader
  -> Cloudflare Access
  -> legacy GET /health + POST /search
  -> sanitized GitHub Artifact
  -> ChatGPT reads the artifact
```

This repository does not receive or duplicate the TGserver ZERO Cloudflare Access service token.

## Runtime producer state

DJPMCP's runtime producer is a separate state from Source / CI. Current runtime acceptance requires evidence that the producer sends P006 logs and that the TGserver ZERO central reader can retrieve the targeted log. A Source or CI PASS alone is not a runtime PASS.

The producer, TGserver ZERO search, Telegram durable storage, and persistent DJPMCP runtime are verified and reported separately.

## Current direct-readback evidence

The latest bounded TGserver ZERO central-reader verification was executed by ChatGPT through owner Issue `seigo-gace/TGserver#43` for canary marker `vps-canary-20261004T025554Z-8cda0ae`, repository `seigo-gace/Deterministic-Japanese-Parser-MCP`, stream `default`, severity `warn`.

- Central-reader workflow run: `37260200579`
- Workflow result: `SUCCESS`
- mapped project: `P006`
- `/health`: HTTP `200`
- `/search`: HTTP `200`
- returned count: `1`
- total hits: `1`
- search completeness: `COMPLETE`
- index health: `HEALTHY`
- index-rebuild risk: `false`
- sanitized artifact: `tgserver-zero-search-37260200579`, artifact id `11324198308`
- ChatGPT Actions job-log readback: `PASS`
- ChatGPT artifact download/readback: `PASS`
- returned hit: `P006` / `warn`, containing the exact canary marker
- TGserver vNext used: `FALSE`
- Cloudflare Access secret duplicated into this repository: `NONE`

The isolated canary producer itself previously passed `CANARY_READY=TRUE`, `P006_LOCAL_READBACK=PASS`, `P006_MARKER_MATCH=PASS`, and `CURRENT_RUNTIME_UNTOUCHED=TRUE`. Together with the current central-reader result, this verifies the bounded DJPMCP producer-to-P006-to-search path without promoting the persistent production runtime.

Telegram durable raw-storage correlation remains a distinct evidence state. A successful targeted Meili search does not by itself prove the raw Telegram receipt for the same record. Persistent production `djpmcp-http` promotion is also a separate approval-bound Runtime state.

## Explicit prohibitions

The Development Probe and TGserver ZERO reader must not provide:

- arbitrary shell commands from Issue text;
- server SSH command execution;
- deploy, restart, recreate, or container mutation;
- Secret creation, rotation, or disclosure;
- Provider or Cloudflare mutation;
- TGserver vNext access;
- direct TGserver reader calls from this repository;
- reuse of another project's TGserver ZERO project ID.

Server/runtime mutations remain subject to the project and server-core approval boundary.

## ChatGPT operating procedure

For source-side evidence:

1. create an owner `[DEV-PROBE]` Issue in this repository after the workflow exists on the default branch;
2. read the Development Probe Actions job logs;
3. read the matching `dev-probe-<run_id>-python-3.10` and `dev-probe-<run_id>-python-3.12` artifacts when report-level evidence is needed;
4. keep Source / Test / CI conclusions separate from Runtime conclusions.

For runtime/server logs:

1. create a `[TGZERO]` Issue in `seigo-gace/TGserver`;
2. request `repo=seigo-gace/Deterministic-Japanese-Parser-MCP` and `stream=default`;
3. provide only bounded search conditions such as query/severity/time range and purpose;
4. read the central reader job log and sanitized artifact;
5. do not copy Cloudflare Access credentials into this repository.

If the central reader cannot retrieve a required runtime log, report that evidence as `NOT_VERIFIED`; do not silently fall back to another project's project ID or TGserver vNext.

## Current completion matrix

```text
PROJECT_AUTHORITY_READ=PASS
CANONICAL_VERIFY_REUSED=PASS
DEV_PROBE_SOURCE=IMPLEMENTED
DEV_PROBE_CI=PASS (branch self-test)
CHAT_ACTIONS_LOG_READBACK=PASS
CHAT_ARTIFACT_READBACK=PASS
TGZERO_PROJECT_REGISTERED=PASS
TGZERO_PRODUCER=VERIFIED (isolated canary)
TGZERO_SEARCH=PASS
SECRET_DUPLICATION=NONE
ARBITRARY_SERVER_COMMAND=NONE
PROJECT_DOCS=UPDATED
OWNER_ISSUE_DEV_PROBE_E2E=NOT_VERIFIED_UNTIL_DEFAULT_BRANCH
PERSISTENT_RUNTIME_PROMOTION=NOT_EXECUTED
TELEGRAM_DURABLE_RECEIPT=NOT_VERIFIED
```
