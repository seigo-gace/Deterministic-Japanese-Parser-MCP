## Summary / 変更概要

- What changed:
- Why this change is needed:
- Public user impact:

## Deterministic behavior / 決定論的挙動

- Input or condition:
- Expected Meaning Graph / Task Graph / dictionary behavior:
- Ambiguous, negative, collision, and fail-closed cases:

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

## Compatibility and limits / 互換性・限界

- Compatibility impact:
- Known limitations:
- Migration or rollback:

## Evidence / Evidence

- Head commit SHA:
- GitHub Actions run:
- Artifact name and digest:
- Related issue or document: