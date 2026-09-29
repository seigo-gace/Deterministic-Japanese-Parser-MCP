# Deterministic Japanese Parser MCP

<p align="center">
  <strong>日本語の語彙・文構造・意味・文脈・曖昧性を、LLMなしで再現可能な構造へ変換する決定論的MCPサーバー</strong>
</p>

<p align="center">
  <strong>日本語</strong> ｜ <a href="README_EN.md">English</a>
</p>

<p align="center">
  <a href="https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP/actions/workflows/ci.yml/badge.svg"></a>
</p>

## 1. 概要

Deterministic Japanese Parser MCP（DJPMCP）は、日本語入力を**生成AIや人間が判断する前段で、検証可能・再利用可能な構造へ変換する非AI・決定論的Parser**です。

主役は回答生成ではありません。入力を単純なIntentラベルへ潰さず、語彙候補、Entity、Clause、Proposition、述語・項、係り受け、否定・条件・数量・モダリティ、引用帰属、照応、談話関係、語義候補、未解決要素などを保持し、中心出力である `MeaningGraph` を形成します。命令・依頼などの実行候補がある場合は、その同じ意味解釈から `TaskGraph` と外部操作可否を導出します。

DJPMCPは次をしません。

- RuntimeでLLMに意味を推測させる
- 根拠のない意味・主語・対象・因果を補う
- Unknownを既知として扱う
- 曖昧な入力を無理に一意化する
- Recovery結果だけを理由に外部操作を許可する
- 外部サービスそのものを操作する

曖昧なら曖昧、不足なら不足、未知なら未知として返し、**判断材料を捏造しないこと**が設計の中心です。

---

## 2. 現在の実装と固定済みTarget Architectureを分けて読む

このRepositoryでは、**現行実装**と**実装中の固定済みTarget Architecture**を混同しません。

| 項目 | 状態 |
|---|---|
| Package Version | `0.4.0` |
| MCP Tool | `analyze_japanese` |
| MCP Transport | stdio / Streamable HTTP |
| Parser REST API | `POST /v1/analyze` |
| Python API | `ParserEngine().analyze(AnalyzeRequest(...))` |
| Python | 3.10以上 |
| 形態解析 | SudachiPy + SudachiDict Core |
| Runtime LLM | 使用しない |
| Runtime外部辞書API | 使用しない |
| MeaningGraph | `2.3.0` を既存Coreとして再利用 |
| TaskGraph / GraphGuard | 既存Coreとして再利用 |
| Program License | MIT |

### 固定済みTarget Architecture

現在の最終設計は次です。

```text
Canonical processed records
  ↓
日本語機能別Projection
  ↓
multi-lane Front Router
  ↓
必要IndexだけProgressive Retrieval
  ↓
Hard Gate
  ↓
Soft Ranking
  ↓
必要時だけRecovery Zone
  ↓
bounded Candidate Lattice
  ↓
whole-sentence Top-K decode
  ↓
Margin / Evidence Gate
  ↓
既存 MeaningGraph 2.3.0
  ↓
TaskGraph
  ↓
GraphGuard
```

このTargetの詳細正本は [`docs/PARSER_ARCHITECTURE.md`](docs/PARSER_ARCHITECTURE.md) です。

**重要:** 設計をRepositoryへ記載したことは実装完了の証拠ではありません。Target Architectureの各層は、Source・Test・Full Build/Audit・性能・Runtime readbackを個別に閉じて初めてPASSになります。

---

## 3. Architectureの最重要原則

### Original is Authority

原文をAuthorityとして保持します。正規化・表記揺れ処理・誤字Recoveryが行われても、原文を上書きしません。

### Evidence only

根拠がないものを補強して「もっともらしい意味」にしません。Sourceが意味を持たない補助Evidenceなら、そのEvidenceから語義を生成しません。

### Ambiguity retention

候補が競合し、Evidence/Score marginが不足する場合は `AMBIGUOUS` / `UNRESOLVED` を維持します。新語や未知表現を自動的に誤字扱いしません。

### Fail closed

`execution_mode="external_action"` では、安全に確定できない重要意味が残ると外部操作を止めます。RecoveryによりAction意味が新しく成立した、または変化した場合も自動許可しません。

### Source / rights / provenance separation

Source全体を一括で「利用可」とみなしません。意味・読み・用法・ランキングEvidence・Provenance等はField-levelで由来と権利を管理するTargetです。

### Runtime without LLM

候補生成、Routing、Lattice、Ranking、Safety Gateまで、Runtimeは非AI・決定論的に閉じます。

---

## 4. 日本語機能別Projection

9,852,513件のCanonical processed recordsを一つの巨大検索対象として毎回総当たりするのではなく、同じCanonical Authorityから**日本語機能別のProjection**を構築する設計です。

Primary laneは以下です。

1. `Orthography/Reading`
2. `Noun-Entity`
3. `Predicate-Inflection`
4. `Function Words`
5. `Connective-Modifier`
6. `Onomatopoeia`
7. `Multiword`
8. `Syntax-Case-Clause`
9. `Sense-Semantic Relation`
10. `Usage-Context-Pragmatics`
11. `Document Structure`
12. `Evidence-Provenance-Rights`

Domain、translation、sentiment、temporal、frequency等はSecondary Facetです。Domain分類だけを主Routerにして意味解釈を決めません。

ProjectionはCanonical Recordの派生View/Indexであり、別の意味正本ではありません。

---

## 5. Front multi-lane RouterとProgressive Retrieval

Front Routerは入力を見て、必要なLane・Facet・Indexを決定論的に選択します。

Routerの責務は**意味を決めることではなく、何を検索すべきかを絞ること**です。

Router Traceでは少なくとも以下を追跡可能にするTargetです。

- 検出した入力Feature
- 選択したLane
- 読まなかったLaneと理由
- 使用したSecondary Facet
- Retrieval制限
- Recovery候補の必要性
- Router/Projection Version

Progressive Retrievalは機能を削る仕組みではありません。必要なEvidenceから段階的に読み、解決できた時点で不要な深い検索を避ける仕組みです。

---

## 6. Purpose Routingの位置付け

Purpose Routingは残しますが、意味の正本にはしません。

Purpose / Source Roleが担当するもの：

- Retrieval Hint
- Role Mask
- Consumer allow/deny
- Permission境界
- Provenance / Ranking / Evidence補助

Purpose Routingが担当しないもの：

- 最終意味の決定
- Japanese-function laneの代替
- 補助Evidenceからの語義生成
- Field-level Rights Gateの迂回
- Unknown Roleの暗黙許可

つまり、**Purposeは「どの材料を誰が使えるか」の補助線であり、「この文はこの意味だ」と決めるAuthorityではありません。**

---

## 7. 誤字・崩れ文・Noisy Input Recovery

### 誤字専用巨大DBは作らない

誤字の全組み合わせを事前登録する方式ではありません。

Target Recovery Flow：

```text
Original Input
  ↓
Safe Normalization
  ↓
Exact / Normal Analysis
  ↓
未解決・OOV・異常分割のみRecovery Zone
  ↓
Surface / Reading / Alias / Morphology / Split-Merge候補
  ↓
Deterministic Recovery Cost
  ↓
Bounded Candidate Lattice
  ↓
Whole-sentence Top-K Decode
  ↓
Grammar / Syntax / Sense / Context / Facet / Evidenceで再評価
  ↓
Margin + Evidence Gate
  ├─ 十分 → Recovery採用
  └─ 不足 → AMBIGUOUS / UNRESOLVED
```

候補ごとに独立修正するのではなく、文全体で競合候補を比較します。

Recoveryでは次を守ります。

- 原文を残す
- 修正候補と採用理由を追跡できる
- 未知語を誤字と断定しない
- Protected Elementを勝手に変えない
- RecoveryでAction意味が変わった場合はFail Closed

---

## 8. Existing MeaningGraph / TaskGraph / GraphGuard

Target Architectureは既存Coreを捨てません。

### MeaningGraph `2.3.0`

現在のCoreは以下のような構造を保持します。

- Entity
- Clause
- Proposition
- Lexical Node
- Scope Edge
- Reading Analysis
- Language Feature
- Unresolved element
- Decision state change
- Evidence rule
- Context version
- Quality annotation
- `semantic_hash`

### Reading Analysis

主な構造：

- `predicate_frames`
- `dependency_arcs`
- `scope_operators`
- `attribution_frames`
- `discourse_relations`
- paragraph/document related analysis
- unresolved reading elements

### TaskGraph

実行候補がある場合、意味解釈からTaskを構造化します。

- Action
- Target
- Dependencies
- Constraints
- Completion criteria
- Verification criteria
- External-action flag

### GraphGuard

External Action時の最終安全境界です。

代表的Blocker：

- 対象未解決
- 重要Reference未解決
- 意味上重要なAmbiguity
- Protected Elementとの衝突
- Contradiction
- Actionに影響するUnsupported要素
- Deadline / Processing failure
- Recoveryにより新規・変更されたAction意味がEvidence Gateを満たさない

停止時は `execution_allowed=false` と `blocked_reasons` を返します。

DJPMCP自身は外部サービスを変更しません。

---

## 9. semantic_hash互換性

現行 `MeaningGraph` は `semantic_hash` 自身を除くGraph内容をHash対象にしています。

そのため、MeaningGraphへDefault Fieldを追加しただけでも、既存入力のHashが変化する可能性があります。

Router Trace、Recovery Evidence、Field-level Rights等をGraphへ接続する前に、**semantic_hash compatibility Gate**を先に実装します。

許されるのは次のどちらかです。

1. 既存Hash契約を変えずExtensionを保持できることをTestで証明する
2. Hash/Graph Version Migrationを明示的に設計・Test・Releaseする

意図しないHash driftは許可しません。

---

## 10. MCP Output Profile Target

MCPは将来、同じSemantic Resultを用途別に運ぶため次のTransport Profileを持ちます。

```text
output_profile = compact | standard | full
Default = full
```

これはCore `AnalyzeRequest` の意味入力ではなく、MCP Transport専用の設定として扱います。

### `full`

既存の完全 `AnalyzeResponse` を維持します。Backward CompatibilityのDefaultです。

### `standard`

Status、Safety、Sentence Semantics、Task、Readingを保持し、Token/Lexical/Paragraph等の重いDetailを必要に応じて省きます。

### `compact`

Status、Safety、Ambiguity/Unresolved、Proposition、`semantic_hash` 等の最小判断材料を保持します。

### 重要な互換条件

- ProfileはParser意味解釈を変えない
- Core `AnalyzeRequest` へ混ぜない
- Cache Identityを変えない
- `semantic_hash` を変えない
- Text SummaryはBackward Compatible
- Default `full` は既存MCP Clientを壊さない

**現在のBaselineではこのProfile実装はまだ未適用です。** 設計済みであることとRuntime実装済みであることを区別します。

---

## 11. 現行MCP / Python Interface

### MCP Tool

```text
analyze_japanese
```

現行Baselineの入力は `AnalyzeRequest` です。

| Field | Required | Default | 内容 |
|---|---:|---|---|
| `original_text` | Yes | — | 解析対象の日本語。空文字不可 |
| `conversation_context` | No | `[]` | 会話文脈 |
| `known_entities` | No | `[]` | 既知Entity |
| `protected_elements` | No | `[]` | 変更禁止対象 |
| `social_context` | No | empty | 話者・相手・社会文脈 |
| `discourse_state` | No | `{}` | 呼出側が保持する談話状態 |
| `execution_mode` | No | `analysis` | `analysis / comparison / planning / external_action` |
| `analysis_depth` | No | `auto` | `auto / fast / deep` |
| `deadline_ms` | No | `50` | 1–60,000ms |

現行の成功MCP Resultは、完全な `AnalyzeResponse` の `structuredContent` と、Status/Execution/Graph count/Task count/Hash等のText Summaryを返します。

MCP Output Profileが実装されるまでは、上記がCurrent Contractです。

### Python API

```python
from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine

response = ParserEngine().analyze(
    AnalyzeRequest(
        original_text="UIは維持する。APIだけ変更しろ。",
        protected_elements=["UI"],
        execution_mode="external_action",
        deadline_ms=50,
    )
)

print(response.meaning_graph)
print(response.task_graph)
print(response.execution_allowed)
```

---

## 12. Public OSS / Self-host Quick Start

### Linux / macOS

```bash
git clone https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP.git
cd Deterministic-Japanese-Parser-MCP
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
djpmcp-validate
```

### Windows PowerShell

```powershell
git clone https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP.git
cd Deterministic-Japanese-Parser-MCP
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .
djpmcp-validate
```

開発用依存関係：

```bash
pip install -e ".[dev]"
```

---

## 13. MCP stdio

Installed entrypoint：

```bash
djpmcp
```

MCP Client例：

```json
{
  "mcpServers": {
    "deterministic-japanese-parser": {
      "command": "/absolute/path/Deterministic-Japanese-Parser-MCP/.venv/bin/djpmcp"
    }
  }
}
```

Windows例：

```text
C:\path\Deterministic-Japanese-Parser-MCP\.venv\Scripts\djpmcp.exe
```

Serving loopへ入る前にprewarmし、Sudachi lazy initialization、Schema、Rule Index、代表経路などをRuntime deadline外で準備します。

---

## 14. Streamable HTTP / REST

HTTP entrypoint：

```bash
djpmcp-http
```

API Key：

```bash
export DJPMCP_HTTP_API_KEY='replace-with-a-long-random-secret'
djpmcp-http
```

既定：

```text
Host: 127.0.0.1
Port: 8765
MCP endpoint: /mcp
Parser REST endpoint: /v1/analyze
Health: /healthz
Readiness: /readyz
```

認証例：

```http
Authorization: Bearer <DJPMCP_HTTP_API_KEY>
```

または：

```http
X-API-Key: <DJPMCP_HTTP_API_KEY>
```

`/healthz` と `/readyz` 以外は認証対象です。

REST例：

```bash
curl -X POST http://127.0.0.1:8765/v1/analyze \
  -H 'Authorization: Bearer YOUR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{
    "original_text": "UIは維持する。APIだけ変更しろ。",
    "protected_elements": ["UI"],
    "execution_mode": "external_action",
    "analysis_depth": "auto",
    "deadline_ms": 50
  }'
```

Production境界は [`docs/PRODUCTION_HTTP_DEPLOYMENT.md`](docs/PRODUCTION_HTTP_DEPLOYMENT.md) を参照してください。

---

## 15. Canonical Data / Supply Chain

DJPMCPは、Raw Source、Canonical Data、Public View、Runtime Projection、Compiled Indexを同一物として扱いません。

概念上の流れ：

```text
Frozen / Verified Source
  ↓
Source Adapter
  ↓
Schema / Provenance / Rights validation
  ↓
Review / Decision Ledger
  ↓
Canonical processed records
  ↓
Japanese-function Projection Compiler
  ↓
Runtime Bundles / Indexes
```

Target Architectureで使用するCanonical processed setは最新設計時点で **9,852,513 records** です。

ただし、新Projection ArchitectureによるFull Build / All-record Auditはまだ実行済みとは扱いません。

詳細：

- [`docs/UNIFIED_SEMANTIC_DATA_PIPELINE.md`](docs/UNIFIED_SEMANTIC_DATA_PIPELINE.md)
- [`docs/OPEN_DICTIONARY_SUPPLY_CHAIN.md`](docs/OPEN_DICTIONARY_SUPPLY_CHAIN.md)
- [`docs/LANGUAGE_DATA_RUNTIME.md`](docs/LANGUAGE_DATA_RUNTIME.md)
- [`docs/DIRECT_FINAL_RUNTIME_DEPLOYMENT.md`](docs/DIRECT_FINAL_RUNTIME_DEPLOYMENT.md)

---

## 16. Logical Runtime Bundles

Targetの初期Logical Bundle：

- `router_core`
- `grammar_core`
- `lexical_semantic`
- `context_evidence`
- `recovery_index`

これは責務分割です。5 Bundle = 5 DBという意味ではありません。

物理DB/File数は以下で決めます。

- build size
- memory footprint
- cold/warm latency
- disk I/O
- deploy atomicity
- rollback
- benchmark結果

---

## 17. Performance

既存Repositoryには狭いScope向けの10ms target / 50ms hard-limit等の契約があります。これらは既存ContractのScopeでは維持します。

一方、Projection + Progressive Retrieval + Recoveryを含む**最終Architecture全体**の固定Acceptance Targetは、定義済みProduction代表Benchmarkで：

```text
p95 < 500 ms
```

です。

これは「遅くしてよい」という意味ではありません。最終機能を削らず、9.85M Canonical Authorityを全件ScanしないRouting/Index構造で閉じるための上限Gateです。より速い既存経路はその性能を維持・改善します。

性能PASSにはLatencyだけでなく、同じ入力・同じ意味結果・同じSafety結果が維持されることが必要です。

---

## 18. Validation / Completion Gate

最終Architectureは次をEvidence付きで閉じるまで「完成」としません。

### Contract

- MCP output profile
- semantic_hash compatibility
- Router Trace
- Recovery Interpretation Evidence
- Field-level Rights / Provenance
- Projection Manifest / Version

### Data

- 9,852,513件 Full Build
- All-record Audit
- Input/Output/Rejected/Unresolved accounting
- Rights/Provenance Audit
- Deterministic rebuild/hash

### Robustness

- Clean Japanese
- Noisy input
- Typo
- Broken/colloquial input
- Segmentation ambiguity
- Unknown/new expression
- False-correction rate
- Ambiguity retention
- Recovery Action fail-closed

### Runtime

- Targeted Tests
- Existing MCP Boundary Tests
- Full Regression
- Production-representative performance
- Authorized deploy
- Runtime readback

Process起動、HTTP 200、空配列、Build成功、Test runner終了、CI greenの一つだけではSemantic completionのPASSにしません。

---

## 19. 固定Implementation Order

```text
M0-1 MCP compact / standard / full
↓
MCP targeted tests
↓
semantic_hash compatibility Gate
↓
Router Trace
↓
Recovery Interpretation Evidence
↓
Field-level Rights / Provenance
↓
Japanese-function Projection Compiler
↓
Front multi-lane Router
↓
Recovery Index / Lattice / Top-K
↓
Progressive Context Retrieval
↓
9.85M Full Build / Audit
↓
Clean + Noisy + Typo + Broken Regression
↓
False-correction / Ambiguity-retention
↓
p95 < 500 ms
↓
Full Regression
↓
Authorized Runtime readback
```

途中工程のPASSから後段を推測でPASSにしません。

---

## 20. Target Architectureの現在Status

このREADME更新時点の境界です。

| Area | Status |
|---|---|
| MeaningGraph / TaskGraph / GraphGuard | 既存実装を再利用 |
| MCP typed base | 既存実装を再利用 |
| Semantic Quality / Holdout | 既存実装を再利用 |
| Direct Final Manifest/Hash | 既存実装を再利用 |
| Purpose Routing | PARTIAL |
| MCP `compact/standard/full` | DESIGN FIXED / SOURCE NOT YET APPLIED at verified baseline |
| semantic_hash compatibility Gate | NOT IMPLEMENTED |
| Router Trace | NOT IMPLEMENTED |
| Recovery Evidence / Index / Lattice / Top-K | NOT IMPLEMENTED |
| Field-level Rights / Provenance Extension | NOT IMPLEMENTED |
| Japanese-function Projection Compiler | NOT IMPLEMENTED |
| Front multi-lane Router | NOT IMPLEMENTED |
| Progressive Context Retrieval | NOT IMPLEMENTED |
| 9.85M Final Rebuild / Audit | NOT RUN |
| Final Robustness | NOT RUN |
| Final p95 < 500ms | NOT RUN |
| Final Full Regression | NOT RUN |
| Target Architecture Runtime Deploy | NOT DEPLOYED |

この表は意図的に保守的です。未検証をPASSにしません。

---

## 21. Public OSSとOfficial Hosted Service

Public OSS / Self-hostとAstera Hosted Commercial Serviceは、Parser Coreの機能を意図的に削る関係ではありません。

### Public OSS

利用者がRepositoryを取得し、自分のPC / Server / Container / Private Network等で実行できます。

利用者側責務：

- Infrastructure
- Authentication
- Monitoring
- Scaling
- Backup
- Availability
- Upgrade / Rollback

### Astera Hosted Commercial Service

Project OwnerがDJPMCPをManaged Runtimeとして運用し、その外側にPlatform Control Planeを置く構成です。

```mermaid
flowchart LR
    U[Customer / AsteraApp] --> G[Astera API Gateway]
    G --> C[Auth / Metering / Credit / Billing / Rate Policy]
    C --> P[DJPMCP Managed Runtime]
    P --> M[MeaningGraph / TaskGraph]
    M --> G
    G --> U
```

Commercial側の主責務：

- Customer Account / Auth
- API Credential Lifecycle
- Authorization
- Usage Metering
- Credit / Quota
- Billing / Plan
- Rate limiting / Abuse protection
- Tenant isolation
- Monitoring
- Version rollout / rollback
- Support / Commercial Terms

Repositoryの `POST /v1/analyze` をそのままCustomer-facing有料APIとして固定しません。

詳細：

- [`docs/COMMERCIAL_AND_DISTRIBUTION_MODEL.md`](docs/COMMERCIAL_AND_DISTRIBUTION_MODEL.md)
- [`docs/ASTERA_HOSTED_API_ARCHITECTURE.md`](docs/ASTERA_HOSTED_API_ARCHITECTURE.md)
- [`docs/PRODUCTION_HTTP_DEPLOYMENT.md`](docs/PRODUCTION_HTTP_DEPLOYMENT.md)

---

## 22. Documentation Map

最初に読むもの：

- [`docs/PARSER_ARCHITECTURE.md`](docs/PARSER_ARCHITECTURE.md) — **固定済み総合Parser Architecture正本**
- [`docs/README.md`](docs/README.md) — Documentation Index

Parser / Data Contract：

- [`docs/JAPANESE_READING_CONTRACT.md`](docs/JAPANESE_READING_CONTRACT.md)
- [`docs/SEMANTIC_QUALITY_CONTRACT.md`](docs/SEMANTIC_QUALITY_CONTRACT.md)
- [`docs/UNIFIED_SEMANTIC_DATA_PIPELINE.md`](docs/UNIFIED_SEMANTIC_DATA_PIPELINE.md)
- [`docs/LANGUAGE_DATA_RUNTIME.md`](docs/LANGUAGE_DATA_RUNTIME.md)
- [`docs/OPEN_DICTIONARY_SUPPLY_CHAIN.md`](docs/OPEN_DICTIONARY_SUPPLY_CHAIN.md)
- [`docs/OPEN_LEXICON_ACCURACY.md`](docs/OPEN_LEXICON_ACCURACY.md)
- [`docs/DIRECT_FINAL_RUNTIME_DEPLOYMENT.md`](docs/DIRECT_FINAL_RUNTIME_DEPLOYMENT.md)
- [`docs/PERFORMANCE_AND_RELEASE_CONTRACT.md`](docs/PERFORMANCE_AND_RELEASE_CONTRACT.md)

Distribution / Operation：

- [`docs/COMMERCIAL_AND_DISTRIBUTION_MODEL.md`](docs/COMMERCIAL_AND_DISTRIBUTION_MODEL.md)
- [`docs/ASTERA_HOSTED_API_ARCHITECTURE.md`](docs/ASTERA_HOSTED_API_ARCHITECTURE.md)
- [`docs/PRODUCTION_HTTP_DEPLOYMENT.md`](docs/PRODUCTION_HTTP_DEPLOYMENT.md)
- [`VALIDATION.md`](VALIDATION.md)
- [`CONTRIBUTING.md`](CONTRIBUTING.md)
- [`SECURITY.md`](SECURITY.md)
- [`GOVERNANCE.md`](GOVERNANCE.md)

---

## 23. License / Data / Brand Boundary

Program CodeのLicense、Third-party DataのSource License、Project Mark/Trademark、Hosted Service Termsは別の権利体系です。

- Program Code: [`LICENSE`](LICENSE)
- Third-party notice: [`NOTICE.md`](NOTICE.md)
- Governance: [`GOVERNANCE.md`](GOVERNANCE.md)
- Trademark: [`TRADEMARK.md`](TRADEMARK.md)

Public Runtimeへ含められるDataかどうかは、Code Licenseだけでは決まりません。

---

## 24. Definition of Done

DJPMCPのTarget Architectureは、**設計文書・Source・Test・Canonical Build/Audit・Robustness・Performance・Full Regression・許可されたRuntime readbackが一致したときだけ完成**です。

それまでは各工程を `PASS / FAIL / PARTIAL / BLOCKED / UNKNOWN / NOT_RUN / NOT_IMPLEMENTED` と分けて管理し、未実施・未検証を完成扱いしません。