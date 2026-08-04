# Documentation Index / 公開ドキュメント案内

このDirectoryは、Deterministic Japanese Parser MCPを利用・検証・拡張する人のためのPublic Documentationです。Repository利用者はNotionや非公開Workspaceを参照しなくても、ここにある資料とSource Codeだけで公開仕様を確認できます。

This directory contains the public documentation required to use, validate, and extend Deterministic Japanese Parser MCP. Users do not need access to Notion or any private workspace.

## Start here / 最初に読む

- [`../README.md`](../README.md) — 概要、Install、MCP設定、Python API、性能・安全性・検証契約
- [`../SUPPORT.md`](../SUPPORT.md) — Bug、質問、改善提案の提出方法
- [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — Contribution要件と検証手順
- [`../SECURITY.md`](../SECURITY.md) — 脆弱性の非公開報告手順
- [`../CHANGELOG.md`](../CHANGELOG.md) — Public変更履歴

## Architecture and contracts / 設計・契約

- [`OPEN_LEXICON_ACCURACY.md`](OPEN_LEXICON_ACCURACY.md) — 12万語JMdict SnapshotのSource Fidelity、Recall、Precision契約
- [`OPEN_DICTIONARY_SUPPLY_CHAIN.md`](OPEN_DICTIONARY_SUPPLY_CHAIN.md) — Open Dictionary取得、変換、Review、Promotion、Rollback
- [`PUBLIC_RELEASE_CHECKLIST.md`](PUBLIC_RELEASE_CHECKLIST.md) — Public Releaseの必須Gate

## Dictionary expansion / 辞書拡張

- [`DICTIONARY_EXPANSION_2026-08.md`](DICTIONARY_EXPANSION_2026-08.md) — 実用表現拡張の選定根拠と第一波
- [`COMPREHENSIVE_DICTIONARY_EXPANSION_2026-08.md`](COMPREHENSIVE_DICTIONARY_EXPANSION_2026-08.md) — 包括辞書拡張の領域・採用基準・検証
- [`../dictionaries/README.md`](../dictionaries/README.md) — Dictionary Directory、Schema、System/User分離
- [`../tools/README.md`](../tools/README.md) — Importer、Reviewer、Promoter、Validatorの実行方法

## Validation evidence / 検証Evidence

GitHub Actionsの`CI`と`Release Readiness`が公開Evidenceの正本です。

- Python 3.10 / 3.12
- Source-tree pytest
- Gold Corpus regression
- Indexed / Exhaustive semantic parity
- Open lexicon provenance and source fidelity
- Exact lookup and ambiguity retention
- Containment and substring-pollution precision
- Offline wheel installation outside the repository
- 20x dictionary scale
- Astera persistent local stdio latency contract

実測値を文書へ掲載する場合は、対応するGitHub Actions Run、Commit SHA、Artifact DigestをPRへ記録します。検証前の数値をPublic実績として扱いません。

When publishing measured results, record the matching GitHub Actions run, commit SHA, and artifact digest in the pull request. Unverified measurements are not treated as public results.