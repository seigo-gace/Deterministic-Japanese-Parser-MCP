# Documentation Index / 公開ドキュメント案内

このDirectoryは、Deterministic Japanese Parser MCPを利用・検証・拡張する人のためのPublic Documentationです。Repository利用者はNotionや非公開Workspaceを参照しなくても、ここにある資料とSource Codeだけで公開仕様を確認できます。

This directory contains the public documentation required to use, validate, and extend Deterministic Japanese Parser MCP. Users do not need access to Notion or any private workspace.

## Start here / 最初に読む

- [`../README.md`](../README.md) — 日本語の概要、導入、使い方、性能、安全性、検証
- [`../README_EN.md`](../README_EN.md) — English overview, installation, usage, performance, safety, and validation
- [`../VALIDATION.md`](../VALIDATION.md) — 第三者検証への参加方法、Discussion Category、Issue化条件
- [`../SUPPORT.md`](../SUPPORT.md) — Discussions、確認済みBug Issue、Security報告の使い分け
- [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — Code・Data Contribution要件と検証手順
- [`../SECURITY.md`](../SECURITY.md) — 脆弱性の非公開報告手順
- [`../CHANGELOG.md`](../CHANGELOG.md) — Public変更履歴

## Community validation / 公開検証

GitHub Discussionsは、第三者検証、判断に迷う結果、日本語表現の確認、導入環境検証、候補DataのEvidence Review、質問、初期アイデアを扱います。

GitHub Issuesは、Maintainerが確認した再現可能な不具合・回帰の修正追跡に限定します。Discussionの投稿は、自動的にBug、採用仕様、Runtime辞書Entry、実装Taskにはなりません。

Discussion Category Form：

- `.github/DISCUSSION_TEMPLATE/validation-campaigns.yml`
- `.github/DISCUSSION_TEMPLATE/validation-results.yml`
- `.github/DISCUSSION_TEMPLATE/japanese-language-review.yml`
- `.github/DISCUSSION_TEMPLATE/environment-validation.yml`
- `.github/DISCUSSION_TEMPLATE/evidence-review.yml`

## Architecture and contracts / 設計・契約

- [`JAPANESE_READING_CONTRACT.md`](JAPANESE_READING_CONTRACT.md) — MCPの第一目的、読解レイヤー、`reading_analysis`、未対応範囲、p95 10ms Gate
- [`SEMANTIC_QUALITY_CONTRACT.md`](SEMANTIC_QUALITY_CONTRACT.md) — Sense、Pragmatics、省略、談話、Reference、安全性の95%品質契約と独立Holdout
- [`OPEN_LEXICON_ACCURACY.md`](OPEN_LEXICON_ACCURACY.md) — 12万語JMdict SnapshotのSource Fidelity、Recall、Precision契約
- [`OPEN_DICTIONARY_SUPPLY_CHAIN.md`](OPEN_DICTIONARY_SUPPLY_CHAIN.md) — Open Dictionary取得、変換、Review、Promotion、Rollback
- [`LANGUAGE_DATA_RUNTIME.md`](LANGUAGE_DATA_RUNTIME.md) — 高度言語FeatureのReview・Promotion・Compile・Runtime反映契約
- [`CONTEXT_V3_STAGE3_REVIEW.md`](CONTEXT_V3_STAGE3_REVIEW.md) — Context v3 5,000件の第3段階Evidence Review（日本語）
- [`CONTEXT_V3_STAGE3_REVIEW_EN.md`](CONTEXT_V3_STAGE3_REVIEW_EN.md) — Context v3 Stage 3 evidence review (English)
- [`PUBLIC_RELEASE_CHECKLIST.md`](PUBLIC_RELEASE_CHECKLIST.md) — Public Releaseの必須Gate

## Dictionary expansion / 辞書拡張

- [`DICTIONARY_EXPANSION_2026-08.md`](DICTIONARY_EXPANSION_2026-08.md) — 実用表現拡張の選定根拠と第一波
- [`COMPREHENSIVE_DICTIONARY_EXPANSION_2026-08.md`](COMPREHENSIVE_DICTIONARY_EXPANSION_2026-08.md) — 包括辞書拡張の領域・採用基準・検証
- [`../dictionaries/README.md`](../dictionaries/README.md) — Dictionary Directory、Schema、System/User分離
- [`../tools/README.md`](../tools/README.md) — Importer、Reviewer、Promoter、Validatorの実行方法

## Validation evidence / 検証Evidence

GitHub Actionsの`CI`と`Release Readiness`が実装検証Evidenceの正本です。第三者のCommunity Validationは、対応するDiscussion、確認済みBug Issue、修正Pull Requestを相互Linkして保持します。

- Python 3.10 / 3.12
- Source-tree pytest
- 167-case supported semantic profile contract
- 130-case independent semantic holdout contract
- External Action Safety 100% contract
- Gold Corpus regression
- Indexed / Exhaustive semantic parity
- Open lexicon provenance and source fidelity
- Exact lookup and ambiguity retention
- Containment and substring-pollution precision
- Context v3 Stage 3 full-accounting and deterministic review packs
- Offline wheel installation outside the repository
- 20x dictionary scale
- Astera persistent local stdio latency contract

実測値を文書へ掲載する場合は、対応するGitHub Actions Run、Commit SHA、Artifact DigestをPull Requestへ記録します。検証前の数値をPublic実績として扱いません。

When publishing measured results, record the matching GitHub Actions run, commit SHA, and artifact digest in the pull request. Unverified measurements are not treated as public results.
