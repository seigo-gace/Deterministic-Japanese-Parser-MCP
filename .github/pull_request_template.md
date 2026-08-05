## Summary / 変更概要

- What changed:
- Why this change is needed:
- Public user impact:

## Deterministic behavior / 決定論的挙動

- Input or condition:
- Expected Meaning Graph / Task Graph / dictionary behavior:
- Ambiguous, negative, collision, and fail-closed cases:

## Contribution rights / Contribution権利確認

- [ ] Every commit contains a valid `Signed-off-by` line under `DEVELOPER_CERTIFICATE_OF_ORIGIN.md`.
- [ ] I identified all contributors, co-authors, employers, third-party materials, generated materials, datasets, and applicable licenses.
- [ ] This contribution contains no confidential material or content I lack authority to submit.
- [ ] Project Owner classified this PR as one of the following:
  - [ ] CLA required — signed agreement accepted and recorded below.
  - [ ] CLA exempt — written exemption recorded below by Project Owner.
  - [ ] Classification pending — **do not merge**.

CLA or exemption record:

- Agreement version:
- Contributor GitHub username:
- Acceptance date:
- Private record identifier or digest:
- Project Owner exemption or acceptance comment:

A checkbox or ordinary PR comment does not replace a signed CLA unless a legally reviewed electronic-signature process has been adopted for the stated Agreement version.

## Governance and brand / Governance・Brand

- [ ] The change follows `GOVERNANCE.md` and does not bypass Project Owner authority.
- [ ] The change does not claim official status, release authority, certification, endorsement, or brand permission that has not been granted.
- [ ] Changes to names, logos, packages, domains, accounts, release branding, or attribution comply with `TRADEMARK.md`.
- [ ] A modified fork or derivative distribution is not presented under official Project Marks.
- [ ] `MAINTAINERS.md`, `GOVERNANCE.md`, `TRADEMARK.md`, or legal documents were updated only with Project Owner approval.

## Validation / 検証

- [ ] `python tools/lexicon_validator.py`
- [ ] `python tools/validator.py`
- [ ] `pytest`
- [ ] `python scripts/test_harness.py`
- [ ] `python scripts/benchmark.py --check`
- [ ] `python scripts/performance_contract.py --check --max-ready-ms 10`
- [ ] `python scripts/astera_latency_contract.py --check --target-ms 10 --hard-ms 50`
- [ ] `python -m compileall -q src tools scripts tests`

Added or updated tests:

- Gold / regression:
- Collision / ambiguity:
- External Action safety:
- Offline / packaging:
- Performance:

## Public repository review / 公開内容確認

- [ ] README or public docs were updated when behavior changed.
- [ ] CHANGELOG records user-visible impact.
- [ ] No secret, credential, personal data, private Notion URL, or local absolute path is included.
- [ ] Third-party data includes source, version, license, attribution, and checksum evidence.
- [ ] No proprietary dictionary definition or corpus sentence was copied.
- [ ] Generated proposals were not auto-promoted into the system dictionary.
- [ ] The MIT code license was not presented as a license to third-party data or Project Marks.

## Compatibility and limits / 互換性・限界

- Compatibility impact:
- Known limitations:
- Migration or rollback:

## Evidence / Evidence

- Head commit SHA:
- GitHub Actions run:
- Artifact name and digest:
- Related issue or document:
