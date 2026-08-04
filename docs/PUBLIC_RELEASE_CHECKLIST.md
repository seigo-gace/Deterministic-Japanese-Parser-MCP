# Public Release Checklist / 公開Release必須条件

このChecklistは、Deterministic Japanese Parser MCPをPublic Repositoryとして更新するときの必須Gateです。内部作業の完了ではなく、第三者がSource、License、検証方法、限界を確認できる状態を完成条件とします。

## 1. Public documentation

- [ ] `README.md`に日本語・英語の概要、Install、利用例、検証、限界、Licenseがある。
- [ ] `CHANGELOG.md`へ利用者影響を記録した。
- [ ] `CONTRIBUTING.md`へ変更要件と実行Commandを記録した。
- [ ] `SUPPORT.md`と`SECURITY.md`が現在の受付方法と一致している。
- [ ] ArchitectureまたはAccuracy変更は`docs/`の契約文書へ反映した。
- [ ] Private Notion URL、秘密情報、個人情報、Local absolute pathをPublic Fileへ含めていない。

## 2. Code and dictionary integrity

- [ ] 同一入力・同一Context・同一Versionで同一結果を返す。
- [ ] `original_text`と原文Spanを保持する。
- [ ] 未確定内容を推測で補完しない。
- [ ] Quote、Question、未解決Reference、矛盾、Timeoutは外部ActionをFail Closedする。
- [ ] Dictionary変更にSource、License、意味、衝突、採用理由、Gold Caseがある。
- [ ] Generated proposalを無審査でSystem Dictionaryへ入れていない。
- [ ] Open lexical identityとProject-authored semantic synonymを混在させていない。

## 3. Automated validation

次がすべて成功していること。

```bash
python tools/lexicon_validator.py
python tools/validator.py
pytest
python scripts/test_harness.py
python scripts/benchmark.py --check
python scripts/performance_contract.py --check --max-ready-ms 10
python scripts/astera_latency_contract.py --check --target-ms 10 --hard-ms 50
python -m compileall -q src tools scripts tests
```

Open Lexiconを含むReleaseでは、Release Readinessで次も成功していること。

- Source SHA-256検証
- 全Runtime RecordのSource Fidelity
- 全Exact Surface Lookup
- 同形異義候補保持
- 包含語Precision
- 文中部分一致汚染検査
- Repository外Offline Install
- 20x Dictionary Scale
- Astera persistent local stdio latency contract

## 4. Pull request evidence

PRには次を残します。

- Base / Head Commit SHA
- 変更理由
- Public利用者への影響
- Test追加内容
- GitHub Actions Run
- Artifact名、Size、SHA-256 Digest
- 既知の限界
- License / Attributionへの影響

## 5. Merge condition

通常CIとRelease Readinessの対象となったHead SHAが、Merge対象Head SHAと一致している場合だけmainへ統合します。文書だけの変更でもPublic Repository Contractを通過させます。

A release or merge is not considered complete when any required public document, regression test, provenance check, accuracy gate, offline installation check, or performance contract fails.