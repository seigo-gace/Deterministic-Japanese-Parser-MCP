# Deterministic Japanese Parser MCP

<p align="center">
  <strong>非AI・非生成・決定論的な日本語解析 / Non-AI, non-generative, deterministic Japanese parsing</strong>
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

### 概要

**Deterministic Japanese Parser MCP**は、日本語の文章から意図・制約・指示対象・比喩表現・実行順序を抽出し、構造化されたTask Packetへ変換する、**非AI・非生成・決定論的なMCP Server**です。

RuntimeでLLMや外部AIを呼び出さず、Version固定された辞書、正規表現Rule、Context解決、矛盾検出、Task分解定義によって処理します。同一入力・同一Context・同一Versionから、同一結果を返すことを目的としています。

このServerは回答文を生成するAIではありません。日本語の入力を、後続Systemが安全に扱える構造へ整理するParserです。

### 主な特徴

| 機能 | 内容 |
|---|---|
| 原文完全保持 | `original_text`を書き換えず、正規化結果を`normalized_text`として分離 |
| 原文位置の追跡 | 抽出結果ごとに`start / end / source_text`を付与 |
| 意図抽出 | 禁止、維持、変更、削除、訂正、決定、比較、条件、例外、優先、順序など21種類 |
| 比喩・慣用句解析 | ContextとDomainを持つ公開辞書を使用 |
| 指示語解決 | 「これ」「それ」「前の案」などを会話Contextから解決 |
| 複数候補保持 | 最初の解釈を勝手に正解として採用しない |
| 情報不足の明示 | 書かれていない主語・対象・条件を推測補完しない |
| 矛盾検出 | 「実装しろ。実装するな。」のような競合を検出 |
| Task分解 | Decision Table型の定義から実行順序付きTask Packetを生成 |
| 外部Action Guard | 曖昧性・矛盾・保護対象競合が残る外部変更を阻止 |
| 部分応答 | 確定部分を保持し、未解決部分を原因別に返却 |
| 辞書分離 | Project標準の`system/`と利用者拡張用の`user/`を分離 |
| 監査可能性 | Parser、辞書、Rule、SchemaのVersion情報を応答へ含める |

### 初期収録データ

- 比喩・慣用表現：**152件**
- 決定論的な意図Pattern：**150件**
- 意図Type：**21種類**
- Task／Workflow Template：**29件**
- 類義語Canonical Group：**20件**
- Gold Corpus：**155件**

収録辞書は、このRepository用に作成したProject独自データです。SudachiPyおよびSudachiDictは外部依存関係であり、それぞれのLicenseに従います。

### 処理構造

```text
MCP Request
    ↓
Input Validation
    ↓
原文保存・Code／URL／数値保護
    ↓
Unicode正規化・原文位置Map生成
    ↓
Sudachi形態素解析
    ↓
Fast Rule Path
    ↓ 必要な場合のみ
比喩・指示語・Context解析
    ↓
矛盾・保護対象競合検出
    ↓
Decision Table型Task分解
    ↓
External Action Guard
    ↓
Structured MCP Response
```

### Status

応答全体は次のいずれかです。

- `COMPLETE`：必要な解析が完了
- `PARTIAL`：確定部分はあるが未解決部分が残る
- `FAILED`：有効な解析結果を返せない

各解析項目は次のStatusを持ちます。

- `RESOLVED`
- `AMBIGUOUS`
- `INSUFFICIENT`
- `CONTRADICTORY`
- `UNSUPPORTED`
- `TIMEOUT`

`TIMEOUT`と`INSUFFICIENT`は別の原因として扱います。

### 必要環境

- Python 3.10以上
- pip
- MCP対応Client、またはPythonからの直接利用

### Install

```bash
git clone https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP.git
cd Deterministic-Japanese-Parser-MCP

python -m venv .venv
```

Linux／macOS：

```bash
. .venv/bin/activate
pip install -e ".[dev]"
```

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

### MCP Serverとして起動

```bash
djpmcp
```

`stdio`で起動し、MCP Toolとして`analyze_japanese`を公開します。

MCP Client設定例：

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

### Pythonから直接利用

```python
from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine

engine = ParserEngine()
response = engine.analyze(
    AnalyzeRequest(
        original_text="今のUIは殺すな。APIだけ変更しろ。",
        execution_mode="external_action",
    )
)

print(response.model_dump_json(indent=2))
```

### 解析例

入力：

```text
障害の火消しをして、落ち着いてから穴を全部塞げ。最後にGitHubへ入れろ。
```

期待されるTask順序：

```text
1. 応急対応
2. 安定確認
3. 設計・実装・検証漏れの解消
4. GitHub反映
```

入力：

```text
まだ実装するな。候補だけ比較して決定しろ。
```

抽出対象：

```text
禁止：実装
対象範囲：候補の比較と決定
順序：候補整理 → 比較 → 決定
```

入力：

```text
実装しろ。実装するな。
```

結果：

```text
CONTRADICTORY
外部Actionは許可しない
```

### 辞書構造

```text
dictionaries/
├── system/                     # Project標準・Version管理対象
│   ├── metaphors/              # Domain別の比喩・慣用表現
│   ├── rules/                  # 意図Type別の決定Rule
│   ├── synonyms.yaml
│   └── task_templates.yaml
└── user/                       # 利用者固有の追加・上書き
    ├── metaphor.json
    ├── rules.yaml
    ├── synonyms.yaml
    └── task_templates.yaml
```

`system/`は公開標準辞書、`user/`は利用者固有の拡張領域です。生成された候補を`system/`へ自動Mergeする機能はありません。

### 未対応Logから今すぐ辞書を改善する

Serverは、未解決結果をMask済みJSONLとして記録できます。

```bash
python tools/learner.py \
  --log logs/parser.jsonl \
  --out proposals/from_logs.yaml

python tools/expander.py \
  --out proposals/synonym_expansion.yaml

python tools/gold_generator.py \
  --log logs/parser.jsonl \
  --out proposals/gold_candidates.json
```

これらは**Review用候補を生成するだけ**です。辞書への自動採用は行いません。

採用する場合は、次を確認してください。

1. 原文の意味と提案が一致している
2. DomainとContextが限定されている
3. 既存RuleやAliasと衝突しない
4. Gold Corpusへ回帰Caseを追加した
5. Validatorと全Testが通過した

### 検証

```bash
python tools/validator.py
pytest
python scripts/test_harness.py
python scripts/benchmark.py
python -m compileall -q src tools scripts tests
```

GitHub Actionsでは、Python 3.10と3.12の両方でValidator、pytest、MCP stdio E2E、compileallを実行します。

### Security

- RuntimeでLLMまたは外部AIを呼び出さない
- 既定で入力本文を外部Networkへ送信しない
- 任意Codeを実行しない
- 入力長、Context数、候補数を制限する
- Regex処理時間を制限する
- Log内の秘密情報・個人情報をMaskする
- 重要な曖昧性が残る外部Actionを許可しない
- 辞書Proposalを自動的に信頼・Mergeしない

### 対象外

- 回答文の生成
- LLMの代替
- 日本語の意味を必ず一つへ決めること
- 不足情報の推測補完
- 未登録業務手順の捏造
- 辞書候補の無審査自動採用

このProjectの目的は、すべての曖昧性を消すことではありません。

> 危険な曖昧性を検出し、原文根拠とともに記録し、未解決のまま実行可能Taskとして確定しないこと。

### Contributing

比喩・慣用表現、意図Rule、Task Template、Gold Corpus、実装修正のContributionを受け付けます。

辞書変更には、次を必須とします。

- 対象となる日本語表現
- 決定可能な解釈またはIntent
- ContextとDomain
- 追加したGold Corpus Case
- `python tools/validator.py`と`pytest`の成功

詳細は[`CONTRIBUTING.md`](CONTRIBUTING.md)を参照してください。

### License

MIT License。詳細は[`LICENSE`](LICENSE)と[`NOTICE.md`](NOTICE.md)を参照してください。

<p align="right"><a href="#deterministic-japanese-parser-mcp">先頭へ戻る</a></p>

---

<a id="english"></a>

## English

### Overview

**Deterministic Japanese Parser MCP** is a **non-AI, non-generative, deterministic MCP server** that extracts intents, constraints, references, figurative expressions, and execution order from Japanese text, then converts them into structured Task Packets.

It does not call an LLM or external AI at runtime. Processing is based on version-locked dictionaries, deterministic regular-expression rules, context resolution, contradiction detection, and task-decomposition definitions. Its goal is to return the same result for the same input, context, and version set.

This server is not an answer-generating AI. It is a parser that converts Japanese input into a structure that downstream systems can handle safely.

### Key Features

| Feature | Description |
|---|---|
| Original text preservation | Never rewrites `original_text`; normalized data is stored separately as `normalized_text` |
| Source-span tracking | Adds `start / end / source_text` to each extracted item |
| Intent extraction | Supports 21 intent types, including prohibition, preservation, modification, removal, correction, decision, comparison, conditions, exceptions, priority, and sequence |
| Metaphor and idiom analysis | Uses public dictionaries with context and domain constraints |
| Anaphora resolution | Resolves references such as “これ”, “それ”, and “前の案” from conversation context |
| Multiple candidates | Never treats the first interpretation as automatically correct |
| Missing-information reporting | Does not invent omitted subjects, targets, or conditions |
| Contradiction detection | Detects conflicts such as “Implement it. Do not implement it.” |
| Task decomposition | Produces ordered Task Packets from decision-table definitions |
| External Action Guard | Blocks external changes when ambiguity, contradiction, or protected-target conflicts remain |
| Partial response | Preserves resolved items and reports unresolved items by cause |
| Dictionary separation | Separates project defaults in `system/` from user extensions in `user/` |
| Auditability | Includes parser, dictionary, rule, and schema versions in responses |

### Included Initial Data

- **152** metaphor and idiom entries
- **150** deterministic intent patterns
- **21** intent types
- **29** task and workflow templates
- **20** canonical synonym groups
- **155** Gold Corpus cases

The bundled dictionary definitions are original project data created for this repository. SudachiPy and SudachiDict are external dependencies and retain their own licenses.

### Processing Architecture

```text
MCP Request
    ↓
Input Validation
    ↓
Original-text preservation and Code / URL / number protection
    ↓
Unicode normalization and original-span mapping
    ↓
Sudachi tokenization
    ↓
Fast Rule Path
    ↓ only when required
Metaphor, reference, and context analysis
    ↓
Contradiction and protected-target conflict detection
    ↓
Decision-table task decomposition
    ↓
External Action Guard
    ↓
Structured MCP Response
```

### Status Model

The overall response uses one of the following states:

- `COMPLETE`: required analysis completed
- `PARTIAL`: resolved items exist, but unresolved items remain
- `FAILED`: no valid analysis result can be returned

Each analysis item uses one of these states:

- `RESOLVED`
- `AMBIGUOUS`
- `INSUFFICIENT`
- `CONTRADICTORY`
- `UNSUPPORTED`
- `TIMEOUT`

`TIMEOUT` and `INSUFFICIENT` are treated as different causes.

### Requirements

- Python 3.10 or later
- pip
- An MCP-compatible client, or direct Python usage

### Installation

```bash
git clone https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP.git
cd Deterministic-Japanese-Parser-MCP

python -m venv .venv
```

Linux / macOS:

```bash
. .venv/bin/activate
pip install -e ".[dev]"
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

### Run as an MCP Server

```bash
djpmcp
```

The server runs over `stdio` and exposes the `analyze_japanese` MCP tool.

Example MCP client configuration:

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

### Direct Python Usage

```python
from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine

engine = ParserEngine()
response = engine.analyze(
    AnalyzeRequest(
        original_text="今のUIは殺すな。APIだけ変更しろ。",
        execution_mode="external_action",
    )
)

print(response.model_dump_json(indent=2))
```

### Analysis Examples

Input:

```text
障害の火消しをして、落ち着いてから穴を全部塞げ。最後にGitHubへ入れろ。
```

Expected task order:

```text
1. Emergency mitigation
2. Stability confirmation
3. Resolution of design, implementation, and validation gaps
4. GitHub integration
```

Input:

```text
まだ実装するな。候補だけ比較して決定しろ。
```

Extracted structure:

```text
Prohibition: implementation
Scope: comparison and decision only
Sequence: organize candidates → compare → decide
```

Input:

```text
実装しろ。実装するな。
```

Result:

```text
CONTRADICTORY
External action is not allowed
```

### Dictionary Structure

```text
dictionaries/
├── system/                     # Versioned project defaults
│   ├── metaphors/              # Domain-specific metaphors and idioms
│   ├── rules/                  # Deterministic rules by intent type
│   ├── synonyms.yaml
│   └── task_templates.yaml
└── user/                       # User-specific additions and overrides
    ├── metaphor.json
    ├── rules.yaml
    ├── synonyms.yaml
    └── task_templates.yaml
```

`system/` contains the public default dictionaries. `user/` is reserved for user-specific extensions. Generated proposals are never merged automatically into `system/`.

### Improve Dictionaries from Unresolved Logs

The server can record unresolved results as masked JSONL.

```bash
python tools/learner.py \
  --log logs/parser.jsonl \
  --out proposals/from_logs.yaml

python tools/expander.py \
  --out proposals/synonym_expansion.yaml

python tools/gold_generator.py \
  --log logs/parser.jsonl \
  --out proposals/gold_candidates.json
```

These commands generate **review candidates only**. They do not update trusted dictionaries automatically.

Before accepting a proposal, verify that:

1. The proposal matches the source text.
2. Its domain and context are properly constrained.
3. It does not conflict with existing rules or aliases.
4. A Gold Corpus regression case has been added.
5. The validator and complete test suite pass.

### Validation

```bash
python tools/validator.py
pytest
python scripts/test_harness.py
python scripts/benchmark.py
python -m compileall -q src tools scripts tests
```

GitHub Actions runs the validator, pytest suite, MCP stdio end-to-end test, and compileall on both Python 3.10 and 3.12.

### Security

- Does not call an LLM or external AI at runtime
- Does not send input text to an external network by default
- Does not execute arbitrary code
- Limits input length, context size, and candidate count
- Applies regex execution limits
- Masks secrets and personal information in logs
- Blocks external actions when critical ambiguity remains
- Never automatically trusts or merges generated dictionary proposals

### Non-Goals

- Generating answer text
- Replacing an LLM
- Forcing every Japanese sentence into one interpretation
- Guessing missing information
- Inventing unregistered business procedures
- Accepting dictionary proposals without review

The goal of this project is not to eliminate every ambiguity.

> The goal is to detect dangerous ambiguity, preserve its source evidence, and prevent unresolved interpretations from becoming executable tasks.

### Contributing

Contributions are welcome for metaphors, idioms, intent rules, task templates, Gold Corpus cases, documentation, and implementation fixes.

Every dictionary change must include:

- The Japanese source expression
- A deterministic interpretation or intent
- Context and domain constraints
- A new Gold Corpus case
- Passing results from `python tools/validator.py` and `pytest`

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for details.

### License

MIT License. See [`LICENSE`](LICENSE) and [`NOTICE.md`](NOTICE.md).

<p align="right"><a href="#deterministic-japanese-parser-mcp">Back to top</a></p>
