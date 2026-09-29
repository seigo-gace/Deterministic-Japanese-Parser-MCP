# Documentation Index / 公開ドキュメント案内

このDirectoryは、Deterministic Japanese Parser MCPを利用・検証・拡張する人、およびPublic OSSとOfficial Hosted Commercial Serviceの境界を確認する人のためのPublic Documentationです。Repository利用者はNotionや非公開Workspaceを参照しなくても、ここにある資料とSource Codeだけで公開仕様を確認できます。

This directory contains the public documentation required to use, validate, extend, self-host, and understand the commercial-service boundaries of Deterministic Japanese Parser MCP. Users do not need access to private project workspaces for the public contract.

## Start here / 最初に読む

- [`../README.md`](../README.md) — 日本語の概要、現行実装とTarget Architectureの境界、導入、API、Data、性能、安全性、検証
- [`PARSER_ARCHITECTURE.md`](PARSER_ARCHITECTURE.md) — **総合Parser Architecture正本。Projection / multi-lane Router / Progressive Retrieval / Recovery / Rights / semantic hash / MCP output profile / 完成Gate**
- [`../README_EN.md`](../README_EN.md) — English overview and usage
- [`COMMERCIAL_AND_DISTRIBUTION_MODEL.md`](COMMERCIAL_AND_DISTRIBUTION_MODEL.md) — Public OSS配布とOfficial Hosted Commercial Serviceの関係
- [`ASTERA_HOSTED_API_ARCHITECTURE.md`](ASTERA_HOSTED_API_ARCHITECTURE.md) — AsteraApp / Astera Platformで有料API化する場合の責務分離
- [`PRODUCTION_HTTP_DEPLOYMENT.md`](PRODUCTION_HTTP_DEPLOYMENT.md) — HTTP RuntimeのProduction配置・認証・Health/Readiness・Secret境界
- [`../VALIDATION.md`](../VALIDATION.md) — 第三者検証への参加方法、Discussion Category、Issue化条件
- [`../SUPPORT.md`](../SUPPORT.md) — Discussions、確認済みBug Issue、Security報告の使い分け
- [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — Code・Data Contribution要件と検証手順
- [`../SECURITY.md`](../SECURITY.md) — 脆弱性の非公開報告手順
- [`../CHANGELOG.md`](../CHANGELOG.md) — Public変更履歴

## Current design status / 現在の設計状態

`PARSER_ARCHITECTURE.md` は、現在固定されている**Target Architecture Contract**です。文書化されたTargetとRuntime実装済み状態を混同しません。

Target flow：

```text
Canonical processed records
→ Japanese-function Projections
→ multi-lane Front Router
→ Progressive Retrieval
→ Hard Gate / Soft Ranking
→ Recovery Zone when required
→ bounded Candidate Lattice / whole-sentence Top-K
→ Margin / Evidence Gate
→ existing MeaningGraph 2.3.0
→ TaskGraph
→ GraphGuard
```

主な境界：

- Canonical processed setの最新設計値は9,852,513件
- Purpose RoleはRetrieval Hint / Permission境界でありMeaning Authorityではない
- 誤字専用巨大DBは作らず、必要時だけbounded Recoveryを行う
- 原文上書き禁止、Unknownを誤字断定しない、曖昧なら曖昧を保持
- Rights / ProvenanceはField-levelで扱うTarget
- MeaningGraphへExtensionを接続する前にsemantic hash互換Gateを置く
- MCP `compact / standard / full` はTransport-only Profileとして実装するTarget
- 新ArchitectureのFull Build / All-record Audit / final robustness / final p95 / Runtime deployは実Evidenceが閉じるまでPASSとしない

個別文書は総合Architectureの各責務を詳細化します。個別Contractと総合Architectureが矛盾した場合は、Source/Test契約と明示されたVersion Migrationを確認し、文書だけで実装状態を上書きしません。

## Architecture and contracts / Parser設計・契約

### [`PARSER_ARCHITECTURE.md`](PARSER_ARCHITECTURE.md)

総合Architectureの正本です。

主な内容：

- Architecture invariants
- 既存MeaningGraph / TaskGraph / GraphGuard再利用境界
- 9.85M Canonical Authorityからの日本語機能別Projection
- Primary 12 LaneとSecondary Facet
- Front multi-lane Router / Router Trace
- Purpose Routingの責務境界
- Progressive Retrieval
- Hard Gate / Soft Ranking
- Noisy/Typo Recovery Zone
- bounded Candidate Lattice / whole-sentence Top-K
- Margin / Evidence Gate
- Field-level Rights / Provenance
- semantic hash Compatibility Gate
- MCP `compact / standard / full`
- Logical Runtime Bundle
- final performance / robustness / regression / runtime Gate
- 固定Implementation Orderと現時点Status

### [`JAPANESE_READING_CONTRACT.md`](JAPANESE_READING_CONTRACT.md)

MCPの日本語読解責務、`reading_analysis`、未対応範囲、既存のScoped Performance Gateを定義します。

### [`SEMANTIC_QUALITY_CONTRACT.md`](SEMANTIC_QUALITY_CONTRACT.md)

Sense、Pragmatics、省略、談話、Reference、安全性の品質契約と独立Holdoutを定義します。

### [`UNIFIED_SEMANTIC_DATA_PIPELINE.md`](UNIFIED_SEMANTIC_DATA_PIPELINE.md)

Raw SourceからCanonical Dataへ至る供給・加工・Review・Provenance・Rights・AccountingのContractです。Target ArchitectureのProjection Compilerは、このCanonical Authorityを消費する後段です。

### [`LANGUAGE_DATA_RUNTIME.md`](LANGUAGE_DATA_RUNTIME.md)

高度Language FeatureのReview・Promotion・Compile・Runtime反映契約です。

### [`OPEN_LEXICON_ACCURACY.md`](OPEN_LEXICON_ACCURACY.md)

Open LexiconのSource Fidelity、Recall、Precision、Ambiguity保持Contractです。

### [`OPEN_DICTIONARY_SUPPLY_CHAIN.md`](OPEN_DICTIONARY_SUPPLY_CHAIN.md)

Open Dictionary取得、変換、Review、Promotion、Rollbackの供給契約です。

### [`DIRECT_FINAL_RUNTIME_DEPLOYMENT.md`](DIRECT_FINAL_RUNTIME_DEPLOYMENT.md)

GitHub管理のRuntime bundleを既存ABIへ投影する手順と境界です。

### [`PERFORMANCE_AND_RELEASE_CONTRACT.md`](PERFORMANCE_AND_RELEASE_CONTRACT.md)

既存のScoped Performance / Release Contractです。総合Target Architectureのfinal p95 GateとはScopeを区別します。

## Distribution, hosted service and deployment / 配布・商用・運用

### [`COMMERCIAL_AND_DISTRIBUTION_MODEL.md`](COMMERCIAL_AND_DISTRIBUTION_MODEL.md)

RepositoryからDownloadしてSelf-hostするPublic OSSと、Project Owner管理ServerをAstera Platform経由で利用するOfficial Hosted Commercial Serviceを分離します。

主な内容：

- MITで公開されるParser Core
- Self-hostとManaged Serviceの責務差
- 商用価値をSource非公開化ではなくManaged Platformへ置く理由
- Commercial Control PlaneとParser Data Planeの境界
- Program License / Third-party Data / Brand / Hosted Termsの分離
- Self-host / Hosted API / Enterprise Private Deploymentへの展開

### [`ASTERA_HOSTED_API_ARCHITECTURE.md`](ASTERA_HOSTED_API_ARCHITECTURE.md)

DJPMCPをAsteraApp / Astera Platformから有料APIとして提供するときの公開Architecture Contractです。

主な内容：

- Astera API Gateway
- Customer Identity / API Credential
- Authorization
- Usage Metering
- Credit / Quota
- Billing boundary
- Rate limit / abuse protection
- Tenant isolation
- Idempotency
- Parser internal versionとCustomer-facing API versionの分離
- Request ID / semantic hash / runtime versionのEvidence関連付け

このDocumentは、Repositoryの`/v1/analyze`をそのままCustomer-facing有料API Contractとして固定しません。

### [`PRODUCTION_HTTP_DEPLOYMENT.md`](PRODUCTION_HTTP_DEPLOYMENT.md)

`djpmcp-http`をProductionへ配置するときのPublic Deployment Guideです。

主な内容：

- `/healthz` / `/readyz`
- Runtime API Key
- Allowed Host / Origin
- request body limit
- DNS rebinding protection
- Docker
- Reverse Proxy / Gateway boundary
- Runtime Dataの固定
- Observability
- Log / retention
- Production SecretをRepositoryへ置かない原則

## Community validation / 公開検証

GitHub Discussionsは、第三者検証、判断に迷う結果、日本語表現の確認、導入環境検証、候補DataのEvidence Review、質問、初期アイデアを扱います。

GitHub Issuesは、Maintainerが確認した再現可能な不具合・回帰の修正追跡に限定します。Discussionの投稿は、自動的にBug、採用仕様、Runtime辞書Entry、実装Taskにはなりません。

Discussion Category Form：

- `.github/DISCUSSION_TEMPLATE/validation-campaigns.yml`
- `.github/DISCUSSION_TEMPLATE/validation-results.yml`
- `.github/DISCUSSION_TEMPLATE/japanese-language-review.yml`
- `.github/DISCUSSION_TEMPLATE/environment-validation.yml`
- `.github/DISCUSSION_TEMPLATE/evidence-review.yml`

## Dictionary expansion / 辞書拡張

- [`DICTIONARY_EXPANSION_2026-08.md`](DICTIONARY_EXPANSION_2026-08.md) — 実用表現拡張の選定根拠と第一波
- [`COMPREHENSIVE_DICTIONARY_EXPANSION_2026-08.md`](COMPREHENSIVE_DICTIONARY_EXPANSION_2026-08.md) — 包括辞書拡張の領域・採用基準・検証
- [`../dictionaries/README.md`](../dictionaries/README.md) — Dictionary Directory、Schema、System/User分離
- [`../tools/README.md`](../tools/README.md) — Importer、Reviewer、Promoter、Validatorの実行方法

## Policy / License / Brand

- [`../LICENSE`](../LICENSE) — Program CodeのMIT License
- [`../NOTICE.md`](../NOTICE.md) — Runtime dependency / Third-party Data notice
- [`../GOVERNANCE.md`](../GOVERNANCE.md) — Official Project、Release、Hosted / Commercial OfferingのAuthority
- [`../TRADEMARK.md`](../TRADEMARK.md) — DJPMCP / Shiori / Astera等の名称・Brandの利用境界
- [`../SECURITY.md`](../SECURITY.md) — Security reporting

Program CodeのMIT License、Third-party DataのSource License、Project Marks、Hosted Service Termsは同一の権利体系ではありません。商用提供時もこの境界を維持します。

## Validation evidence / 検証Evidence

GitHub ActionsのCIやRelease Readiness、Source/Test/Artifactのreadbackが実装検証Evidenceです。

代表的なGate：

- Python 3.10 / 3.12
- Source-tree pytest
- MCP boundary / schema compatibility
- semantic hash compatibility
- supported semantic profile contract
- independent semantic holdout contract
- External Action Safety contract
- Gold Corpus regression
- Indexed / Exhaustive semantic parity
- Open lexicon provenance and source fidelity
- Exact lookup and ambiguity retention
- Containment and substring-pollution precision
- Canonical/Projection full accounting
- Rights / provenance audit
- Noisy/Typo/Broken-text robustness
- False-correction / ambiguity-retention metrics
- Offline wheel installation outside the repository
- Production-representative latency / p95 contract

実測値を文書へ掲載する場合は、対応するCommit SHA、GitHub Actions Run、Artifact Digest、Runtime/Provider readback等、対象Scopeに必要なEvidenceを紐付けます。検証前の数値をPublic実績として扱いません。

When publishing measured results, record the matching commit, CI/runtime evidence, and artifact digest required for that claim. Unverified measurements are not treated as public results.