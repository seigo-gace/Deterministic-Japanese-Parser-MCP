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

**Deterministic Japanese Parser MCP**は、日本語入力を単なるIntent一覧ではなく、文・命題・対象・条件・例外・禁止・維持・引用・疑問・訂正・依存関係を接続した**Meaning Graph**へ変換する、非AI・非生成・決定論的なMCP Serverです。

RuntimeでLLMや外部AIを呼び出しません。Sudachiによる形態情報、Version固定された辞書、事前CompileしたRule Index、決定論的Grammar Kernel、Scope解決、会話Context、矛盾検出、Task Graph、External Action Guardによって処理します。

このServerは回答文を生成しません。後続Systemが、日本語の指示を安全に処理するための構造を返します。

### 現在の辞書規模

| データ | 件数 |
|---|---:|
| 比喩・慣用表現 | **200** |
| 決定論的Intent Pattern | **213** |
| Intent Type | **21** |
| 類義語Canonical Group | **40** |
| Task / Workflow Template | **39** |
| Workflow | **18** |
| Gold Corpus | **271** |

2026年8月の拡張では、既存の開発・設計中心の語彙に加え、日常指示、業務Communication、担当移管、合意形成、障害切り分け、再現確認、暫定／恒久対応、文書構造、日本語校正に関する表現を追加しました。

追加した主な表現例：

- 日常指示：`一旦置く`、`巻き取る`、`持ち越す`、`手短にまとめる`
- 業務Communication：`すり合わせる`、`話を通す`、`根回しする`、`宿題にする`
- 開発・運用：`切り分ける`、`再現を取る`、`ログを追う`、`影響範囲を洗う`
- 文書・読解：`骨子を作る`、`肉付けする`、`噛み砕く`、`ねじれを直す`

候補一覧、意味・意図、採用理由、誤検出Risk、保留・除外理由は[`docs/DICTIONARY_EXPANSION_2026-08.md`](docs/DICTIONARY_EXPANSION_2026-08.md)に記録しています。

### 辞書拡張の調査方針

候補は最初から少数へ限定せず、広く収集した後に次を確認します。

1. 現代の書き言葉・日常会話・業務・開発で実際に使われる、または使われる可能性が高いか。
2. 文字通りの意味と比喩・業務上の意味を区別できるか。
3. Action、Constraint、状態、談話機能のどれへ変換するか。
4. 既存EntryやAliasと衝突しないか。
5. 自然なGold Corpus Caseを作成できるか。
6. 外部Actionを誤って許可するRiskがないか。

使用傾向と用語確認には、国立国語研究所のBCCWJ・CEJC・日本語Webコーパス関連資料、GitHub公式Document、デジタル庁デザインシステム、Microsoft Learnの技術文書Guideline等を参照します。外部辞書の定義文やコーパス本文はコピーせず、`interpretation`は本Project用に独自記述します。

短く多義的な表現は無条件に確定しません。たとえば`切り分ける`は「調査」「分解」「原因特定」の複数Canonical候補を保持します。比喩側では周辺Contextが一致しない場合、`AMBIGUOUS`として扱います。

### 設計原則

- `original_text`を変更しない。
- 正規化結果と原文Spanを分離して保持する。
- Rule一致を最終的な意味決定にしない。Ruleは候補とEvidenceを供給する。
- Meaning Graphを意味の唯一の正本とする。
- 旧`intents`と旧`tasks`は互換Viewとして残す。
- 維持・禁止・条件・例外は、原則として独立ActionではなくTask Constraintとして扱う。
- 引用内、疑問文、反語候補、未解決参照を外部Actionとして実行しない。
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

追加した63 Intent Patternはすべて固定Literalを持ち、Rule Indexへ載る構造です。追加した48比喩・慣用表現は一件ごとにGold Caseを持ちます。

「辞書が無限に増えても計算量が変わらない」とは保証しません。Releaseでは、非一致大量辞書、同一入力への大量一致、意味衝突、Domain衝突、Context増加、Graph Node増加、Astera call-throughを検証します。

### 追加Workflow

既存Workflowに加えて、以下を収録しています。

- Requirement Analysis
- Bug Reproduction
- Root Cause Analysis
- Document Revision
- Data Migration
- Dependency Upgrade
- Account / Authentication Change
- UI Accessibility Review
- Knowledge Base Update
- Rollback / Recovery

各Workflowは準備・実行・検証・記録を省略しません。

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

GitHub ActionsではPython 3.10 / 3.12、MCP stdio E2E、Indexed / Exhaustive意味同値、辞書Scale、全追加Entry Coverage、Astera call-through、Offline Wheel Install、Release Manifestを検証します。

### Security

- RuntimeでLLMまたは外部AIを呼び出さない。
- 入力本文を外部Networkへ送信しない。
- 引用・疑問・未解決参照をActionへ昇格しない。
- 重要なScope未解決、矛盾、TimeoutではFail Closedする。
- 保護対象への変更をBlockする。
- Logの秘密情報・個人情報をMaskする。
- 辞書Proposalを自動採用しない。

### 現在の限界

本MCPは、任意の日本語を人間と同等に理解すると保証するものではありません。現在のMeaning Graphは、Version固定された文法・Rule・辞書で根拠を説明できる範囲を構造化します。皮肉、暗黙の常識、複雑なゼロ代名詞、複数段落の談話解釈など、確定できない内容を推測で埋めません。

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

- 200 metaphor and idiomatic-expression entries
- 213 deterministic intent patterns across 21 intent types
- 40 canonical synonym groups
- 39 task/workflow templates, including 18 workflows
- 271 Gold Corpus cases

The August 2026 expansion adds everyday instructions, business communication, ownership transfer, agreement building, incident diagnosis, reproduction testing, temporary/permanent fixes, document structure, and Japanese-writing review expressions.

Candidate sourcing and review are documented in [`docs/DICTIONARY_EXPANSION_2026-08.md`](docs/DICTIONARY_EXPANSION_2026-08.md). Usage tendencies are checked against NINJAL BCCWJ, CEJC, Japanese web-corpus resources, and official technical documentation. External dictionary definitions and corpus passages are not copied; interpretations are authored for this project.

### Core guarantees

- Preserve `original_text` and source spans.
- Treat rules as candidate/evidence detectors, not the final semantic authority.
- Use `meaning_graph` as the single semantic source of truth.
- Keep legacy `intents` and `tasks` as compatibility views.
- Represent preservation, prohibition, conditions, and exceptions as Task constraints rather than independent actions.
- Never execute quoted or interrogative command candidates.
- Return explicit unresolved states rather than inventing omitted meaning.
- Return the same Semantic Hash for the same input, context, and version.
- Require one Gold case for every new metaphor and every new rule.

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

### Dictionary scale

The runtime uses indexed, versioned dictionary snapshots and does not linearly scan every registered literal. All 63 newly added intent patterns contain mandatory indexable literals. CI verifies coverage for every new metaphor and rule, indexed/exhaustive semantic parity, collision handling, dictionary scale, and latency.

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

### Validation

```bash
python tools/validator.py
pytest
python scripts/benchmark.py --check
python scripts/performance_contract.py --check --max-ready-ms 10
python scripts/astera_latency_contract.py --check --target-ms 10 --hard-ms 50
python -m compileall -q src tools scripts tests
```

CI validates Python 3.10 and 3.12, MCP stdio E2E, all expanded-entry coverage, indexed/exhaustive semantic parity, dictionary scale, Astera call-through latency, offline wheel installation, and evidence manifests.

### Scope and limitations

This project does not claim human-level understanding of arbitrary Japanese. It deterministically structures the meaning that can be supported by versioned grammar, rules, dictionaries, and context. It fails closed when quotation, reference, scope, discourse, or pragmatic intent cannot be resolved safely.

### License

MIT License. See [`LICENSE`](LICENSE) and [`NOTICE.md`](NOTICE.md).
