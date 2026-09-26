# Documentation Index / 公開ドキュメント案内

このDirectoryは、Deterministic Japanese Parser MCPを利用・検証・拡張・Self-hostするためのPublic Documentationです。Public OSSとOfficial Hosted Commercial Serviceの境界もここから確認できます。Repository利用者はNotionや非公開Workspaceを参照しなくても公開仕様を追える構成にします。

## Start here / 最初に読む

- [`../README.md`](../README.md) — 3分Quick Start、日本語概要、実Runtime Sample
- [`../README_EN.md`](../README_EN.md) — English quick start; Japanese README is the primary project README
- [`API_REFERENCE.md`](API_REFERENCE.md) — MCP / REST / Python API contract
- [`CONFIGURATION.md`](CONFIGURATION.md) — Parser / HTTP environment variables and runtime configuration
- [`DEVELOPMENT_AND_CI.md`](DEVELOPMENT_AND_CI.md) — Development install, CI gates, evidence, README sample generation
- [`SOURCE_MAP.md`](SOURCE_MAP.md) — Major implementation paths and responsibility boundaries

## Parser architecture and contracts / Parser設計・契約

- [`JAPANESE_READING_CONTRACT.md`](JAPANESE_READING_CONTRACT.md) — 第一目的、読解Layer、`reading_analysis`、未対応範囲、performance boundary
- [`SEMANTIC_QUALITY_CONTRACT.md`](SEMANTIC_QUALITY_CONTRACT.md) — Sense、Pragmatics、省略、Discourse、Reference、安全性Quality Contract
- [`PERFORMANCE_AND_RELEASE_CONTRACT.md`](PERFORMANCE_AND_RELEASE_CONTRACT.md) — Performance / Release Gate
- [`LANGUAGE_DATA_RUNTIME.md`](LANGUAGE_DATA_RUNTIME.md) — Language Feature / semantic runtimeのReview・Promotion・Compile・Runtime反映契約
- [`DIRECT_FINAL_RUNTIME_DEPLOYMENT.md`](DIRECT_FINAL_RUNTIME_DEPLOYMENT.md) — GitHub-managed completed Runtime Bundleを既存ABIへ投影する手順
- [`PUBLIC_RELEASE_CHECKLIST.md`](PUBLIC_RELEASE_CHECKLIST.md) — Public Releaseの必須Gate

## Dictionary / lexical data

- [`OPEN_LEXICON_ACCURACY.md`](OPEN_LEXICON_ACCURACY.md) — JMdict-derived Open LexiconのSource Fidelity、Recall、Precision契約
- [`OPEN_DICTIONARY_SUPPLY_CHAIN.md`](OPEN_DICTIONARY_SUPPLY_CHAIN.md) — Open Dictionary取得、変換、Review、Promotion、Rollback
- [`DICTIONARY_EXPANSION_2026-08.md`](DICTIONARY_EXPANSION_2026-08.md) — 実用表現拡張
- [`COMPREHENSIVE_DICTIONARY_EXPANSION_2026-08.md`](COMPREHENSIVE_DICTIONARY_EXPANSION_2026-08.md) — 包括辞書拡張
- [`CONTEXT_V3_STAGE3_REVIEW.md`](CONTEXT_V3_STAGE3_REVIEW.md) / [`CONTEXT_V3_STAGE3_REVIEW_EN.md`](CONTEXT_V3_STAGE3_REVIEW_EN.md) — Context v3 Stage 3 Evidence Review
- [`../dictionaries/README.md`](../dictionaries/README.md) — Dictionary directories / schema
- [`../tools/README.md`](../tools/README.md) — Importer / reviewer / promoter / validator tooling

## Distribution, hosted service and production / 配布・商用・運用

- [`COMMERCIAL_AND_DISTRIBUTION_MODEL.md`](COMMERCIAL_AND_DISTRIBUTION_MODEL.md) — Public OSS / Self-host とOfficial Hosted Commercial Serviceの責務境界
- [`ASTERA_HOSTED_API_ARCHITECTURE.md`](ASTERA_HOSTED_API_ARCHITECTURE.md) — Astera API Gateway、Customer identity、Metering、Credit/Billing、Tenant、Version境界
- [`PRODUCTION_HTTP_DEPLOYMENT.md`](PRODUCTION_HTTP_DEPLOYMENT.md) — HTTP Runtime、Authentication、Health/Readiness、Allowed Host/Origin、Secret、Gateway境界

Repositoryの`POST /v1/analyze`はParser Runtime Interfaceであり、それ自体をCustomer-facing paid API contractとはみなしません。Commercial Control PlaneはParser Data Planeと分離します。

## Community / contribution / policy

- [`../VALIDATION.md`](../VALIDATION.md) — Third-party validation
- [`../SUPPORT.md`](../SUPPORT.md) — Discussion / Bug / Security channel separation
- [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — Code / Data contribution requirements
- [`../SECURITY.md`](../SECURITY.md) — Private vulnerability reporting
- [`../CHANGELOG.md`](../CHANGELOG.md) — Public change history
- [`../LICENSE`](../LICENSE) — Program Code MIT License
- [`../NOTICE.md`](../NOTICE.md) — Runtime dependency / Third-party Data notices
- [`../GOVERNANCE.md`](../GOVERNANCE.md) — Official Project / Release / Hosted Commercial authority
- [`../TRADEMARK.md`](../TRADEMARK.md) — DJPMCP / Shiori / Astera brand boundary

## Validation evidence / 検証Evidence

GitHub ActionsのCI / Release Readinessを実装検証EvidenceのAuthorityとして扱います。代表的なGateは次です。

- Python 3.10 / 3.12
- Deployment preflight
- Runtime lexicon provenance / license validation
- Dictionary / Gold validation
- Supported semantic quality contract
- Independent semantic holdout contract
- Unit / integration / MCP stdio E2E
- Benchmark regression
- 20x dictionary performance contract
- Astera 10ms target / 50ms hard-limit contract
- compile validation
- Evidence artifact preservation

実測値を公開する場合は、対応するCommit SHA、GitHub Actions Run、Python Version、Artifact Digestを関連付けます。未検証値をPublic実績として扱いません。
