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

The temporary `push` trigger is limited to the current integration branch and only the Development Probe/document paths. It exists so the probe source itself can be verified before a main merge. The normal request path is the owner-only `[DEV-PROBE]` Issue trigger.

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

TGserver ZERO central-reader verification was executed from owner Issue `seigo-gace/TGserver#36` for the bounded canary marker `vps-canary-20261004T025554Z-8cda0ae` with repository `seigo-gace/Deterministic-Japanese-Parser-MCP`, stream `default`, and severity `warn`.

- Central-reader workflow run: `37256729067`
- Workflow result: `SUCCESS`
- mapped project: `P006`
- `/health`: reachable through the configured ZERO route
- `/search`: successful
- returned count: `1`
- estimated total: `1`
- search completeness: `FULL_COMPLETE`
- remaining estimate: `0`
- index health: `HEALTHY`
- negative evidence state: `HIT_PRESENT`
- sanitized artifact: `tgserver-zero-search-37256729067`, artifact id `11322479070`
- ChatGPT Actions job-log readback: `PASS`
- ChatGPT artifact download/readback: `PASS`
- returned hit: P006 / warn and contains the exact canary marker
- TGserver vNext used: `FALSE`
- Cloudflare secret duplicated into this repository: `NONE`

The returned record is a legacy-time-schema hit. The ZERO audit schema therefore reports `PRODUCER_VERIFIED=false`, `FULL_INDEX_COVERAGE_NOT_PROVEN`, and `TELEGRAM_RAW_CORRELATION=NOT_PRESENT_IN_RETURNED_HITS`. These fields are not promoted to PASS by the successful targeted search. The prior canary proves the project producer could deliver a P006 record that the legacy search index returns; persistent-runtime adoption of the current producer revision and Telegram durable correlation remain separate evidence states.

Development Probe source is implemented on the current integration branch. Its branch-scoped push self-test is triggered by changes to this evidence document. Owner-Issue execution is not treated as available until `.github/workflows/dev-probe.yml` exists on the default branch.

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
