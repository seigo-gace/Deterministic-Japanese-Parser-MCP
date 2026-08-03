# Deterministic Japanese Parser MCP

<p align="center">
  <strong>非AI・非生成・決定論的に、日本語をMeaning Graphへ変換するMCP Server</strong><br>
  <strong>Non-AI, non-generative, deterministic Japanese-to-Meaning-Graph MCP server</strong>
</p>

<p align="center">
  <a href="#日本語">日本語</a> ｜ <a href="#english">English</a>
</p>

<p align="center">
  <a href="https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Python 3.10+" src="https://img.shields.io/badge/Python-3.10%2B-blue">
  <img alt="MCP" src="https://img.shields.io/badge/MCP-Server-6366f1">
  <img alt="License MIT" src="https://img.shields.io/badge/License-MIT-yellow">
</p>

---

<a id="日本語"></a>

## 日本語

### これは何か

**Deterministic Japanese Parser MCP**は、日本語入力を単なるIntent一覧ではなく、文・命題・対象・条件・例外・禁止・維持・引用・疑問・訂正・依存関係・会話修復・語用機能を接続した**Meaning Graph**へ変換する、非AI・非生成・決定論的なMCP Serverです。

RuntimeでLLMや外部AIを呼び出しません。Sudachiによる形態情報、Version固定された辞書、事前CompileしたRule Index、決定論的Grammar Kernel、Scope解決、会話Context、矛盾検出、Task Graph、External Action Guardによって処理します。

このServerは回答文を生成しません。後続Systemが、日本語の指示・制約・判断・参照・含意候補を安全に処理するための構造を返します。

### 現在の辞書規模

| データ | 件数 |
|---|---:|
| 比喩・慣用・語用表現 | **452** |
| 決定論的Intent Pattern | **339** |
| Intent Type | **21** |
| 類義語Canonical Group | **100** |
| Task / Workflow Template | **63** |
| Workflow | **42** |
| Gold Corpus | **649** |

### 2026年8月の包括拡張

第一波の実用語彙追加を出発点に、第二波では次の14領域へ**252表現**を追加しました。

1. 会話修復・認識合わせ
2. 時系列・進捗・停滞・日程変更
3. 否定・制約・範囲外・例外管理
4. 感情・態度・反応・信頼
5. 計画・意思決定・Risk
6. 障害・Debug・復旧
7. 文書構成・説明・推敲
8. Collaboration・担当・責任・Escalation
9. Data・API・Integration
10. Security・Privacy・Governance
11. UI・UX・Accessibility
12. Sales・Support・Customer
13. 日常口語の短い指示
14. 婉曲拒否・保留・懸念・確認要求

追加例：

- 会話修復：`話を戻す`、`認識差を埋める`、`すれ違いを解く`、`意図を汲み直す`
- 進行状態：`目処を立てる`、`足踏みする`、`遅れを取り戻す`、`積み残しを消化する`
- 制約：`抜け道を塞ぐ`、`条件を絞り込む`、`入口で足切りする`、`範囲を閉じる`
- 判断Risk：`先に手を打つ`、`逃げ道を作る`、`選択肢を残す`、`最悪を織り込む`
- 障害復旧：`止血を優先する`、`原因候補を潰す`、`復旧線を残す`、`監視を張る`
- 文書読解：`係り受けをほどく`、`行間を読む`、`読み筋を作る`、`言い切りを弱める`
- Security：`鍵を回す`、`権限を絞る`、`秘密を伏せる`、`監査経路を残す`
- UI/UX：`導線を引く`、`情報を畳む`、`読み順を整える`、`操作を迷わせる`
- 日常口語：`ちょっと置いとく`、`ぱっと見る`、`ざっと洗う`、`念のため見る`
- 間接表現：`今は難しいです`、`その点は確認が必要です`、`その案には懸念があります`

全追加表現・意味・Domain・採用基準・保留語・検証契約は、[`docs/COMPREHENSIVE_DICTIONARY_EXPANSION_2026-08.md`](docs/COMPREHENSIVE_DICTIONARY_EXPANSION_2026-08.md)に記録しています。第一波の監査記録は[`docs/DICTIONARY_EXPANSION_2026-08.md`](docs/DICTIONARY_EXPANSION_2026-08.md)にあります。

### Pattern拡張

既存21 Intent Typeすべてへ6 Patternずつ、合計**126 Pattern**を追加しました。

- `action`
- `comparison`
- `completion_criteria`
- `condition`
- `correction`
- `decision`
- `dependency`
- `exception`
- `modify`
- `out_of_scope`
- `premise`
- `preserve`
- `priority`
- `prohibition`
- `question`
- `reference`
- `remove`
- `request`
- `scope`
- `sequence`
- `verification_criteria`

新規Ruleは、Compile成功だけでは採用済みになりません。全Ruleについて、固定LiteralによるIndex登録、専用Gold文でのRegex一致、最終Meaning側でのIntent一致、Indexed / Exhaustive意味同値を検証します。`prohibition`と`out_of_scope`はExternal Actionを必ずBlockします。

### 類義語とWorkflow

Canonical Groupは40群から**100群**へ増やしました。会話修復、再確認、再評価、遅延、監視、追跡、復旧準備、代替案、Risk低減、期待調整、Scope確定、権限制限、匿名化、暗号化、監査、構文確認、校正、推敲、間接拒否、保留回答、Escalation、顧客案内などを追加しています。

Workflowは18件から**42件**へ増やしました。追加した主なWorkflow：

- Dialogue Repair
- Ambiguity Resolution
- Scope Freeze
- Risk Review
- External Action Safety
- Privacy Review
- Secret Rotation
- Access Review
- Incident Communication
- Observability Setup
- Data Contract Change
- Safe Schema Migration
- Webhook Integration
- API Deprecation
- Mobile Release
- Responsive UI Review
- Accessibility Remediation
- Customer Onboarding
- Support Deflection
- Pricing Change
- Payment Flow Change
- Content Publication
- Localization Review
- Repository Publication

各追加Workflowは7段階の順序付きStepsを持ち、準備・実行・検証・記録を省略しません。

### 分割辞書構造

将来の大規模拡張で巨大Fileを直接書き換え続けないよう、次のFragment Directoryを追加しました。

```text
dictionaries/system/
├── synonyms.yaml
├── synonyms.d/
│   └── *.yaml
├── task_templates.yaml
└── task_templates.d/
    └── *.yaml
```

Loaderは元の正本Fileを先に読み、Fragmentを名前順で読み込み、重複を決定論的に統合します。Offline WheelにもFragment Directoryを含め、Repository外Installで読込可能かを検証します。

### 辞書拡張の調査方針

候補を最初から少数へ限定せず、現代書き言葉、日常会話、職場会話、Web日本語、技術Documentの領域を横断して収集し、次を確認します。

1. 実際の日本語で使われる、または十分に使われる可能性があるか。
2. 文字通りの意味と比喩・業務・語用上の意味を区別できるか。
3. Action、Constraint、状態、談話機能、態度、判断保留のどれへ変換するか。
4. 既存Entry・Alias・Canonical Groupと衝突しないか。
5. 自然なGold Corpus Caseを一件ずつ作成できるか。
6. 外部Actionを誤って許可するRiskがないか。
7. 丁寧さだけから上下関係・承認・拒否を断定していないか。

使用傾向と用語確認には、国立国語研究所のBCCWJ1・BCCWJ2・CEJC・CSJ・職場会話・日本語Webコーパス関連資料、GitHub公式Document、デジタル庁、Microsoft、W3C等の一次資料を参照します。外部辞書の定義文やコーパス本文はコピーせず、`interpretation`、Pattern、Gold Caseは本Project用に独自記述します。

`やばい`、`えぐい`、`神`、`回す`、`落とす`、`刺す`、`飛ばす`など、単独では世代・Community・Domain・文脈により意味や極性が変わり過ぎる語は、無条件Mappingを行いません。識別可能な長い構文または十分なContext条件ができるまで保留します。

### 設計原則

- `original_text`を変更しない。
- 正規化結果と原文Spanを分離して保持する。
- Rule一致を最終的な意味決定にしない。Ruleは候補とEvidenceを供給する。
- Meaning Graphを意味の唯一の正本とする。
- 旧`intents`と旧`tasks`は互換Viewとして残す。
- 維持・禁止・条件・例外は、原則として独立ActionではなくTask Constraintとして扱う。
- 引用内、疑問文、反語候補、未解決参照を外部Actionとして実行しない。
- 婉曲拒否・保留・懸念・確認要求を同一の肯定Intentへ潰さない。
- 確定不能な内容は推測せず、`AMBIGUOUS`、`INSUFFICIENT`、`UNSUPPORTED`、`TIMEOUT`として返す。
- 同一入力・同一Context・同一Versionから同一Semantic Hashを返す。

### 処理構造

```text
Astera / MCP Request
    ↓
Input Contract・50ms Hard Deadline
    ↓
原文保存・Unicode正規化・Original Span Map
    ↓
Sudachi形態情報
    ↓
Indexed Rule / Metaphor Candidate Detection
    ↓
Deterministic Grammar Kernel
    ├─ Clause境界
    ├─ Mood / Speech Act
    ├─ Predicate / Argument候補
    ├─ Quote / Negation / Modality
    └─ Topic / Focus候補
    ↓
Meaning Graph
    ├─ Entity
    ├─ Clause
    ├─ Proposition
    ├─ Argument
    ├─ Typed Scope Edge
    └─ Decision State Change
    ↓
Contradiction・Reference・Scope検証
    ↓
Action Task Graph + Structured Constraints
    ↓
Action-Relevance External Guard
    ↓
Legacy Intent / Task Compatibility Views
    ↓
Schema検証済みStructured Response
```

### Responseの中心

```json
{
  "meaning_graph": {
    "semantic_hash": "...",
    "entities": [],
    "clauses": [],
    "propositions": [],
    "scope_edges": [],
    "unresolved": [],
    "decision_state_changes": []
  },
  "task_graph": {
    "tasks": [],
    "edges": [],
    "constraints": []
  },
  "execution_allowed": false,
  "blocked_reasons": []
}
```

`intents`と`tasks`も引き続き返しますが、新規連携では`meaning_graph`と`task_graph`を使用してください。

### ActionとConstraintの分離

入力：

```text
UIは維持する。APIだけ変更しろ。
```

意味：

```text
Action: APIを変更する
Constraint: UIを維持する
Constraint: 対象範囲はAPIだけ
```

「UIを維持する」を、API変更後に実行する別Taskとして誤って並べません。

### 引用・疑問を実行しない

```text
「全データを削除しろ」と彼は言った。
```

引用内の削除命令候補はMeaning Graphへ記録しますが、`executable_candidate=false`となり、外部Actionは許可されません。

```text
全データを削除しろという意味なのか？
```

疑問文を削除命令として実行しません。

### Status

応答全体：`COMPLETE` / `PARTIAL` / `FAILED`

項目単位：

- `RESOLVED`
- `AMBIGUOUS`
- `INSUFFICIENT`
- `CONTRADICTORY`
- `UNSUPPORTED`
- `TIMEOUT`

### 性能契約

Asteraの回答処理全体目標は**100ms以内**です。このうち本MCPは次を契約します。

| 境界 | 条件 |
|---|---:|
| 常駐Kernel内部の最適目標 | 5ms以下 |
| Astera側Call開始から検証済みResponse受渡しまでの通常目標 | p95 10ms以下 |
| 同じ測定境界の絶対上限 | 50ms以下 |
| 50msまでに確定不能 | `TIMEOUT`を返し外部ActionをBlock |

測定には、常駐済みlocal stdio、Decode、事前Compile済みPydantic Schemaによる完全検証、Meaning Graph、Task Graph、Guard結果の受領までを含みます。Process起動、辞書読込、Regex Compile、Index構築、Sudachi初期化、Schema CompileはReady前に完了させます。

### 辞書量と速度

辞書を毎回全走査しません。

- Literal Rule / Metaphor：Aho-Corasick型Index
- 活用・機能表現：事前Compileされた決定表
- 述語・Domain辞書：Key別Index
- User辞書：System辞書と分離
- 実行中の辞書：Version固定Snapshot

追加した126 Intent Patternはすべて固定Literalを持ち、Rule Indexへ載る構造です。追加した252表現は一件ごとに専用Gold Caseを持ちます。

「辞書が無限に増えても計算量が変わらない」とは保証しません。Releaseでは、非一致大量辞書、同一入力への大量一致、意味衝突、Domain衝突、Context増加、Graph Node増加、Astera call-throughを検証します。

### Install

```bash
git clone https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP.git
cd Deterministic-Japanese-Parser-MCP
python -m venv .venv
```

Linux / macOS：

```bash
. .venv/bin/activate
pip install -e ".[dev]"
```

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

### MCP Server

```bash
djpmcp
```

```json
{
  "mcpServers": {
    "deterministic-japanese-parser": {
      "command": "djpmcp",
      "args": []
    }
  }
}
```

公開Tool：`analyze_japanese`

### Pythonから利用

```python
from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine

response = ParserEngine().analyze(
    AnalyzeRequest(
        original_text="UIは維持する。APIだけ変更しろ。",
        execution_mode="external_action",
        deadline_ms=50,
    )
)

print(response.meaning_graph.model_dump_json(indent=2))
print(response.task_graph.model_dump_json(indent=2))
print(response.execution_allowed)
```

### 検証

```bash
python tools/validator.py
pytest
python scripts/test_harness.py
python scripts/benchmark.py --check
python scripts/performance_contract.py --check --max-ready-ms 10
python scripts/astera_latency_contract.py --check --target-ms 10 --hard-ms 50
python -m compileall -q src tools scripts tests
```

GitHub Actionsでは次を検証します。

- Python 3.10 / 3.12
- MCP stdio E2E
- 452表現・339 Rule・100 Canonical Group・63 Template・42 Workflow・649 Goldの固定件数
- 252追加表現の全件実検出
- 126追加RuleのIndex登録・Regex一致・最終Intent一致
- Indexed / Exhaustive意味同値
- 辞書ScaleとLatency
- Astera call-through 10ms目標 / 50ms上限
- Offline Wheel InstallとRepository外Import
- Release ManifestとEvidence Hash

### Security

- RuntimeでLLMまたは外部AIを呼び出さない。
- 入力本文を外部Networkへ送信しない。
- 引用・疑問・未解決参照をActionへ昇格しない。
- 重要なScope未解決、矛盾、TimeoutではFail Closedする。
- 保護対象への変更をBlockする。
- Logの秘密情報・個人情報をMaskする。
- 辞書Proposalを自動採用しない。

### 現在の限界

本MCPは、任意の日本語を人間と同等に理解すると保証するものではありません。現在のMeaning Graphは、Version固定された文法・Rule・辞書で根拠を説明できる範囲を構造化します。皮肉、暗黙の常識、複雑なゼロ代名詞、複数段落の談話解釈、地域差・世代差が大きい俗語など、確定できない内容を推測で埋めません。

### Contributing

辞書・Grammar・Meaning Graph・Gold Corpus変更には、候補一覧、意味・意図、採用／保留／除外理由、期待構造、衝突Case、全Entry Coverage、全Testと性能結果を添付してください。詳細は[`CONTRIBUTING.md`](CONTRIBUTING.md)を参照してください。

### License

MIT License。詳細は[`LICENSE`](LICENSE)と[`NOTICE.md`](NOTICE.md)を参照してください。

---

<a id="english"></a>

## English

### Overview

**Deterministic Japanese Parser MCP** is a non-AI, non-generative, deterministic MCP server that transforms Japanese input into a typed **Meaning Graph** instead of only returning a flat list of intents.

It does not call an LLM or external AI at runtime. It combines Sudachi morphological information, version-locked dictionaries, precompiled rule indexes, a deterministic grammar kernel, typed scope relations, context resolution, contradiction detection, an action Task Graph, and a fail-closed External Action Guard.

### Dictionary volume

| Data | Count |
|---|---:|
| Metaphor, idiom, and pragmatic expressions | **452** |
| Deterministic intent patterns | **339** |
| Intent types | **21** |
| Canonical synonym groups | **100** |
| Task / workflow templates | **63** |
| Workflows | **42** |
| Gold Corpus cases | **649** |

### Comprehensive August 2026 expansion

The second expansion wave adds 252 expressions across dialogue repair, temporal progress, constraints, attitude and feedback, planning and risk, incident recovery, document revision, ownership and escalation, data/API integration, security and privacy, UI/UX accessibility, customer support, casual spoken instructions, and indirect pragmatic speech acts.

All expressions and adoption decisions are documented in [`docs/COMPREHENSIVE_DICTIONARY_EXPANSION_2026-08.md`](docs/COMPREHENSIVE_DICTIONARY_EXPANSION_2026-08.md).

Every existing intent type receives six additional practical patterns, for 126 new rules. Each rule must be compiled, selected by the literal index, matched by a dedicated Gold sentence, and preserved as the intended final semantic type. New prohibition and out-of-scope rules must deny external-action execution.

### Modular dictionaries

Large canonical additions can be stored under:

```text
dictionaries/system/synonyms.d/*.yaml
dictionaries/system/task_templates.d/*.yaml
```

The original canonical files load first. Fragments load in deterministic filename order and are merged without losing overlapping canonical forms. Both directories are included in offline wheels and verified outside the repository.

### Core guarantees

- Preserve `original_text` and source spans.
- Treat rules as candidate/evidence detectors, not the final semantic authority.
- Use `meaning_graph` as the single semantic source of truth.
- Keep legacy `intents` and `tasks` as compatibility views.
- Represent preservation, prohibition, conditions, and exceptions as Task constraints rather than independent actions.
- Never execute quoted or interrogative command candidates.
- Preserve indirect refusal, hesitation, concern, and information requests as distinct pragmatic evidence.
- Return explicit unresolved states rather than inventing omitted meaning.
- Return the same Semantic Hash for the same input, context, and version.
- Require dedicated Gold coverage for every new expression and rule.

### Architecture

```text
Request
  → normalization and source-span map
  → Sudachi morphology
  → indexed rule/metaphor candidates
  → deterministic grammar kernel
  → Meaning Graph
  → scope, reference and contradiction validation
  → action Task Graph + constraints
  → action-relevance guard
  → schema-validated MCP response
```

### Main response models

- `meaning_graph.entities`
- `meaning_graph.clauses`
- `meaning_graph.propositions`
- `meaning_graph.scope_edges`
- `meaning_graph.unresolved`
- `task_graph.tasks`
- `task_graph.constraints`
- `execution_allowed`
- `blocked_reasons`

### Latency contract

| Boundary | Contract |
|---|---:|
| Optimized resident kernel goal | <= 5 ms |
| Normal Astera-side call-through target | p95 <= 10 ms |
| Absolute call-through hard limit | <= 50 ms |
| Unresolved at hard deadline | Return `TIMEOUT` and block external action |

The call-through boundary includes a persistent local stdio call, decoding, precompiled Pydantic output-schema validation, and delivery of the complete Meaning Graph, Task Graph, and Guard result. Cold start and index/schema compilation complete before readiness.

### Validation contract

CI validates:

- Python 3.10 and 3.12
- MCP stdio end-to-end behavior
- fixed totals of 452 expressions, 339 rules, 100 synonym groups, 63 templates, 42 workflows, and 649 Gold cases
- actual detection of all 252 second-wave expressions
- index selection, regex matching, and final semantic type for all 126 second-wave rules
- indexed/exhaustive semantic parity
- dictionary-scale and latency contracts
- Astera call-through target and hard limit
- offline wheel installation and repository-external import
- release evidence manifests and hashes

### Install and run

```bash
git clone https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP.git
cd Deterministic-Japanese-Parser-MCP
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
djpmcp
```

Windows PowerShell activation:

```powershell
.\.venv\Scripts\Activate.ps1
```

### Python example

```python
from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine

response = ParserEngine().analyze(
    AnalyzeRequest(
        original_text="UIは維持する。APIだけ変更しろ。",
        execution_mode="external_action",
        deadline_ms=50,
    )
)

print(response.meaning_graph)
print(response.task_graph)
```

### Validation commands

```bash
python tools/validator.py
pytest
python scripts/benchmark.py --check
python scripts/performance_contract.py --check --max-ready-ms 10
python scripts/astera_latency_contract.py --check --target-ms 10 --hard-ms 50
python -m compileall -q src tools scripts tests
```

### Scope and limitations

This project does not claim human-level understanding of arbitrary Japanese. It deterministically structures meaning that can be supported by versioned grammar, rules, dictionaries, and context. It fails closed when quotation, reference, scope, discourse, or pragmatic intent cannot be resolved safely.

### License

MIT License. See [`LICENSE`](LICENSE) and [`NOTICE.md`](NOTICE.md).
