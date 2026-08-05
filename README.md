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

<!-- project-control-top:start -->
<p align="center">
  <strong>Created and maintained by Seigo Kato (<a href="https://github.com/seigo-gace">@seigo-gace</a>).</strong><br>
  <strong>設計・開発・管理：加藤星悟（<a href="https://github.com/seigo-gace">@seigo-gace</a>）</strong><br>
  Official project direction, releases, contribution acceptance, and brand permissions are controlled by the Project Owner.
</p>

<p align="center">
  <a href="MAINTAINERS.md">Owner &amp; Maintainers</a> ｜
  <a href="GOVERNANCE.md">Governance</a> ｜
  <a href="TRADEMARK.md">Trademark Policy</a> ｜
  <a href="CONTRIBUTING.md">Contributing</a> ｜
  <a href="CONTRIBUTOR_LICENSE_AGREEMENT.md">CLA</a>
</p>
<!-- project-control-top:end -->

---

<a id="日本語"></a>

## 日本語

### これは何か

**Deterministic Japanese Parser MCP**は、日本語入力を単なるIntent一覧ではなく、文・命題・対象・条件・例外・禁止・維持・引用・疑問・訂正・依存関係・会話修復・語用機能を接続した**Meaning Graph**へ変換する、非AI・非生成・決定論的なMCP Serverです。

RuntimeでLLMや外部AIを呼び出しません。Sudachiによる形態情報、Version固定された辞書、事前CompileしたRule Index、決定論的Grammar Kernel、Scope解決、会話Context、矛盾検出、Task Graph、External Action Guardによって処理します。

このServerは回答文を生成しません。後続Systemが、日本語の指示・制約・判断・参照・含意候補を安全に処理するための構造を返します。

### 現在の実収録規模

| データ | 件数 |
|---|---:|
| 比喩・慣用・語用表現 | **452** |
| 決定論的Intent Pattern | **339** |
| Intent Type | **21** |
| 類義語Canonical Group | **100** |
| Task / Workflow Template | **63** |
| Workflow | **42** |
| Gold Corpus | **649** |
| Open lexical records | **0** |

`Open lexical records`は、Source checkoutに固定収録している外部辞書Record数です。巨大な未審査Dumpはmainへ固定せず、Release Readinessで公式Sourceから加工・照合したSnapshotをWheelへ同梱します。

検証済みRelease Snapshotは、公式JMdictから加工した**120,000 Record**です。Runtimeは外部辞書へ接続せず、加工済みSnapshotを完全Offlineで読み込みます。

### 2026年8月の包括辞書拡張

第一波と第二波を通じて、次の14領域へ実用表現を追加しました。

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

詳細：

- [`docs/DICTIONARY_EXPANSION_2026-08.md`](docs/DICTIONARY_EXPANSION_2026-08.md)
- [`docs/COMPREHENSIVE_DICTIONARY_EXPANSION_2026-08.md`](docs/COMPREHENSIVE_DICTIONARY_EXPANSION_2026-08.md)

### 無料辞書を使う継続追加Pipeline

骨格だけだった`learner.py`、`expander.py`、`gold_generator.py`を、無料・機械可読の辞書資源から継続的に辞書を増やせるSupply Chainへ完成させました。

対応Source：

| Source | 使用内容 | Data License |
|---|---|---|
| Japanese Wiktionary | 日本語語釈、品詞、慣用句、類義語、関連語、活用候補 | CC BY-SA / GFDL |
| Wikidata Lexemes | Lemma、Form、Sense、Lexical Category、構造化関係 | CC0 |
| JMdict | 表記、読み、読み制約、品詞、分野、用法、Cross Reference | CC BY-SA |
| SudachiDict source CSV | 表記、読み、品詞、正規化形 | Apache 2.0 |
| Masked unresolved logs | 実利用上の不足候補 | Review専用・公開Pack昇格禁止 |

処理順：

```text
Official Open Dump / Masked Runtime Log
    ↓
Atomic Download + SHA-256 Source Manifest
    ↓
Source-specific Importer
    ↓
Common Lexicon JSONL
    ↓
learner.py
    ├─ 既存Metaphor Surface衝突
    ├─ 既存Rule Pattern衝突
    ├─ 既存Canonical Surface衝突
    └─ Source／License Evidence
    ↓
expander.py
    ├─ Surface／Form補強
    ├─ Alias候補
    └─ 多義Surface分離
    ↓
gold_generator.py
    ├─ 肯定
    ├─ 否定
    ├─ 引用
    ├─ 疑問
    └─ External Action Guard候補
    ↓
reviewer.py
    ├─ 意味・意図確認
    ├─ 衝突解決
    ├─ 肯定例・否定例
    └─ External Action確認
    ↓
promoter.py --apply --performance
    ├─ License別Runtime Pack
    ├─ Metaphor／Rule／Synonym Fragment
    ├─ Review済みGold
    ├─ Source Manifest
    ├─ README／Manifest／Version同期
    ├─ 全回帰・Offline・正確性・性能検証
    └─ Failure時の全Rollback
```

詳細な実行Command：[`tools/README.md`](tools/README.md)

設計・Review・License・Rollback契約：[`docs/OPEN_DICTIONARY_SUPPLY_CHAIN.md`](docs/OPEN_DICTIONARY_SUPPLY_CHAIN.md)

### 12万語Open Lexiconの正確性検証

旧Snapshotを実データで再検証した結果、読みをCanonical別名へ混ぜたことと、日本語の任意部分文字列を検索したことにより、通常文から無関係な語彙候補が発生する問題を確認しました。旧Snapshotでは`UIは維持する。APIだけ変更しろ。`だけで**73件**の無関係候補が発生していました。

現在は次へ修正しています。

- JMdictの1 Entryを1 Source Recordとして保持
- 表記と読みを分離し、`re_restr`／`re_nokanji`を保存
- 読みをCanonical Aliasへ自動昇格しない
- Open Lexiconを完全一致専用とし、通常文の部分一致検索から分離
- 意味・用法をReviewしたProject独自Synonymだけを文中検索
- 別語である短い語と長い包含語を、文字列包含だけで同一視しない

公式JMdictからBuildした120,000 Recordを全件照合し、次を確認しました。

| Accuracy Gate | 結果 |
|---|---:|
| Source Fidelity | **120,000 / 120,000** |
| Exact Surface Lookup | **154,918 / 154,918** |
| 同形異義Surface | **962件、全候補保持** |
| 包含語Precision | **20,000 / 20,000** |
| 文中部分一致汚染 | **20,000 / 20,000、誤一致0** |
| Accuracy Error | **0** |

詳細：[`docs/OPEN_LEXICON_ACCURACY.md`](docs/OPEN_LEXICON_ACCURACY.md)

### Source別Importer

```text
tools/dictionary_supply/importers/
├── wiktionary.py
├── wikidata_lexemes.py
├── jmdict.py
└── sudachi_csv.py
```

各Sourceを共通Schemaへ変換します。

```json
{
  "record_id": "...",
  "lemma": "...",
  "readings": [],
  "reading_mappings": [
    {
      "reading": "...",
      "restricted_to": [],
      "no_kanji": false
    }
  ],
  "surfaces": [],
  "part_of_speech": [],
  "lexical_category": null,
  "senses": [],
  "forms": [],
  "synonyms": [],
  "antonyms": [],
  "related": [],
  "domains": [],
  "usage_labels": [],
  "source": {
    "dataset": "...",
    "version": "...",
    "license": "...",
    "source_id": "...",
    "source_url": "...",
    "source_sha256": "...",
    "attribution": "..."
  },
  "review_status": "needs_review"
}
```

同じJMdict Entryの表記と読みをCross Productへ展開しません。読みはMetadataとして保持し、表記Aliasには自動昇格しません。同じ完全一致Surfaceが複数Canonicalを持つ場合は候補集合として保持します。

### License別Runtime Pack

```text
dictionaries/system/lexicon.d/
├── cc0/
├── apache-2.0/
├── cc-by-sa/
└── copyleft-other/
```

MITのProgram Codeと外部辞書DataのLicenseを同一扱いにしません。各RecordへSource License、Version、Source ID、URL、SHA-256、Attributionを保持します。

以下はRuntime Packへ昇格できません。

- `review_status`が`approved`以外
- `PRIVATE-REVIEW-ONLY`
- License不明
- Source ID欠落
- 未解決のSurface／Meaning衝突
- Gold、全回帰、External Action、安全性、正確性、性能Gateの未通過

### Transactional Promotion

`promoter.py`はDry Runを既定とし、`--apply`を指定した場合だけ書き込みます。

```bash
python tools/promoter.py \
  --bundle reviewed/2026-08-open-lexicon.yaml \
  --batch-id 2026-08-open-lexicon

python tools/promoter.py \
  --bundle reviewed/2026-08-open-lexicon.yaml \
  --batch-id 2026-08-open-lexicon \
  --apply \
  --performance
```

書込前に対象FileをBackupし、Validator、pytest、compileall、正確性Gate、20倍辞書、Astera call-throughのいずれかが失敗した場合は、新規Fileを削除し、変更前のFileをByte単位で復元します。

### Pattern・類義語・Workflow

既存21 Intent Typeへ実用Patternを追加しています。

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

新規RuleはCompile成功だけでは採用しません。固定LiteralによるIndex登録、専用Gold文でのRegex一致、最終Meaning側でのIntent一致、Indexed／Exhaustive意味同値を検証します。

WorkflowはDialogue Repair、Ambiguity Resolution、Scope Freeze、Risk Review、External Action Safety、Privacy Review、Incident Communication、Data Contract Change、Safe Schema Migration、Webhook Integration、API Deprecation、Mobile Release、Responsive UI Review、Accessibility Remediation、Customer Onboarding、Support Deflection、Pricing Change、Payment Flow Change、Content Publication、Localization Review、Repository Publicationなどを含みます。

### 分割辞書構造

```text
dictionaries/system/
├── metaphors/
├── rules/
├── lexicon.d/
├── synonyms.yaml
├── synonyms.d/
│   └── *.yaml
├── task_templates.yaml
└── task_templates.d/
    └── *.yaml
```

Loaderは正本File、Fragment、承認済みLexicon Packを決定論的に読み込みます。Open Lexiconの表記は完全一致専用として統合し、読みを別名へ昇格せず、通常文の部分文字列検索へ混ぜません。意味・用法をReviewしたProject独自Synonymだけを文中検索します。一つの完全一致Surfaceが複数Canonicalを持つ場合は衝突を隠さず候補集合として保持します。

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
- 自動生成Proposalを無審査でSystem辞書へ入れない。
- Runtimeから外部辞書をDownloadしない。

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

新規連携では`meaning_graph`と`task_graph`を使用してください。`intents`と`tasks`も互換Viewとして返します。

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

引用内の命令候補はMeaning Graphへ記録しますが、外部Actionは許可されません。

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

Process起動、辞書読込、Regex Compile、Index構築、Sudachi初期化、Schema CompileはReady前に完了させます。

### 辞書量・正確性・速度

辞書を毎回全走査しません。

- Literal Rule／Metaphor：Aho-Corasick型Index
- 活用・機能表現：事前Compileされた決定表
- 述語・Domain辞書：Key別Index
- Review済みSynonym：Canonical Trie
- Open Lexicon：完全一致Index
- User辞書：System辞書と分離
- 実行中の辞書：Version固定Snapshot

「辞書が無限に増えても計算量が変わらない」とは保証しません。Releaseでは、Source全件一致、Exact Recall、包含語Precision、文中汚染、非一致大量辞書、同一入力への大量一致、意味衝突、Domain衝突、Context増加、Graph Node増加、Astera call-throughを検証します。

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
python tools/lexicon_validator.py
python tools/validator.py
pytest
python scripts/test_harness.py
python scripts/benchmark.py --check
python scripts/performance_contract.py --check --max-ready-ms 10
python scripts/astera_latency_contract.py --check --target-ms 10 --hard-ms 50
python -m compileall -q src tools scripts tests
```

実JMdict Accuracy GateはRelease Readinessで次を実行します。

```bash
python tools/open_lexicon_accuracy.py \
  --source downloads/JMdict_e.gz \
  --lexicon-root dictionaries/system/lexicon.d \
  --manifest reports/open-lexicon-manifest.json \
  --minimum-records 100000 \
  --containment-cases 20000 \
  --pollution-cases 20000 \
  --output reports/open-lexicon-accuracy.json
```

GitHub Actionsでは次を検証します。

- Python 3.10／3.12
- Japanese Wiktionary／Wikidata Lexemes／JMdict／Sudachi Importer Fixture
- Common Lexicon Schema Round Trip
- JMdict Entry／Reading Restriction保持
- Proposal Source／License Evidence
- Review GateとConflict Resolution
- Private Logの公開Pack昇格拒否
- License別Runtime Pack
- Runtime Lexicon Provenance
- 公式JMdictと加工後Packの全Record一致
- 全Exact Surface Lookup
- 同形異義候補保持
- 20,000包含語Precision
- 20,000文中部分一致汚染
- MCP stdio E2E
- 452表現・339 Rule・100 Canonical Group・63 Template・42 Workflow・649 Goldの既存回帰
- Indexed／Exhaustive意味同値
- 辞書ScaleとLatency
- Astera call-through 10ms目標／50ms上限
- Offline Wheel InstallとRepository外Import
- Release ManifestとEvidence Hash

### Security

- RuntimeでLLMまたは外部AIを呼び出さない。
- Runtimeで外部辞書をDownloadしない。
- 入力本文を外部Networkへ送信しない。
- Private Logを公開辞書Packへ昇格しない。
- 引用・疑問・未解決参照をActionへ昇格しない。
- 重要なScope未解決、矛盾、TimeoutではFail Closedする。
- 保護対象への変更をBlockする。
- Logの秘密情報・個人情報をMaskする。
- 辞書Proposalを自動採用しない。
- Source、License、Checksum、Attributionを失ったRecordを読み込まない。
- 読みを表記Aliasとして無審査昇格しない。

### 現在の限界

本MCPは、任意の日本語を人間と同等に理解すると保証するものではありません。現在のMeaning Graphは、Version固定された文法・Rule・辞書で根拠を説明できる範囲を構造化します。皮肉、暗黙の常識、複雑なゼロ代名詞、複数段落の談話解釈、地域差・世代差が大きい俗語など、確定できない内容を推測で埋めません。

Open Dictionary Supply Chainは大量候補の取得・変換・審査・昇格を自動化しますが、辞書の語釈を自動的に実行可能Intentへ変換するものではありません。12万語Accuracy Contractは語彙識別情報の正確性を検証するものであり、12万語すべての語義・語用理解を保証するものではありません。意味・Scope・安全性を確認したProposalだけを意味辞書へ昇格します。

### Contributing

辞書・Grammar・Meaning Graph・Gold Corpus変更には、候補一覧、Source／License、意味・意図、採用／保留／除外理由、期待構造、衝突Case、全Entry Coverage、全Testと性能結果を添付してください。詳細は[`CONTRIBUTING.md`](CONTRIBUTING.md)を参照してください。

<!-- project-control-ja:start -->
### Project Owner・Brand・Governance

**設計・開発・管理：加藤星悟（[`@seigo-gace`](https://github.com/seigo-gace)）。** 公式Repository、Roadmap、Architecture、Release、Contribution採択、Project Marksの使用許可に関する最終決定権は、[`GOVERNANCE.md`](GOVERNANCE.md)に従ってProject Ownerが保持します。

Program CodeはMIT Licenseで無料利用・改変・再配布できます。ただし、MIT Licenseは`Deterministic Japanese Parser MCP`、`DJPMCP`、`Shiori MCP Server`、公式Logo、`Astera`等のBrandを使って、改変Fork・製品・Serviceを公式と表示する権利を与えません。Brand利用は[`TRADEMARK.md`](TRADEMARK.md)に従います。

外部ContributionはDCOが必須です。実質的なCode、辞書、Gold、設計、Release、Security、Governance変更は、Merge前にProject Ownerが受領した[`CONTRIBUTOR_LICENSE_AGREEMENT.md`](CONTRIBUTOR_LICENSE_AGREEMENT.md)を必要とします。詳細は[`CONTRIBUTING.md`](CONTRIBUTING.md)を参照してください。
<!-- project-control-ja:end -->

### License

Program CodeはMIT Licenseです。詳細は[`LICENSE`](LICENSE)と[`NOTICE.md`](NOTICE.md)を参照してください。

外部辞書から昇格したDataは、Recordおよび`dictionaries/sources/`のManifestに記録された各Source Licenseへ従います。

---

<a id="english"></a>

## English

### Overview

**Deterministic Japanese Parser MCP** is a non-AI, non-generative, deterministic MCP server that transforms Japanese input into a typed **Meaning Graph** instead of only returning a flat list of intents.

It does not call an LLM or external AI at runtime. It combines Sudachi morphological information, version-locked dictionaries, precompiled rule indexes, a deterministic grammar kernel, typed scope relations, context resolution, contradiction detection, an action Task Graph, and a fail-closed External Action Guard.

### Current promoted data

| Data | Count |
|---|---:|
| Metaphor, idiom, and pragmatic expressions | **452** |
| Deterministic intent patterns | **339** |
| Intent types | **21** |
| Canonical synonym groups | **100** |
| Task / workflow templates | **63** |
| Workflows | **42** |
| Gold Corpus cases | **649** |
| Open lexical records | **0** |

`Open lexical records` counts external records committed to the source checkout. Large unreviewed dumps are not pinned to main. Release Readiness builds, transforms, audits, and bundles an offline snapshot from the official source.

The verified release snapshot contains **120,000 JMdict records**. Runtime never connects to the external dictionary.

### Open dictionary supply chain

The original learner, expander, and Gold-generator skeletons are now a complete, repeatable pipeline for adding large open Japanese dictionary resources.

Supported inputs:

- Japanese Wiktionary XML dumps
- Wikidata Lexeme JSON dumps
- JMdict XML
- SudachiDict source CSV
- masked unresolved runtime logs as private review evidence

```text
Open dump or masked log
  → atomic download and SHA-256 manifest
  → source-specific importer
  → common lexicon JSONL
  → collision-aware proposal bundle
  → sense-safe expansion
  → Gold candidate matrix
  → mandatory human review
  → transactional promotion
  → accuracy, regression, offline and performance gates
```

Detailed commands: [`tools/README.md`](tools/README.md)

Architecture and review contract: [`docs/OPEN_DICTIONARY_SUPPLY_CHAIN.md`](docs/OPEN_DICTIONARY_SUPPLY_CHAIN.md)

### Verified accuracy of the 120k open lexicon

A full-data audit found that the previous snapshot mixed readings into canonical aliases and scanned arbitrary Japanese substrings. As a concrete failure, `UIは維持する。APIだけ変更しろ。` produced **73 unrelated lexical candidates**.

The corrected design keeps one source-traceable record per JMdict entry, preserves `re_restr` and `re_nokanji`, never promotes readings as orthographic aliases, and isolates open lexical identities from phrase substring scans. Only project-authored, meaning-reviewed synonym groups remain eligible for phrase scanning.

The release gate independently compared the official JMdict dump with the generated runtime pack:

| Accuracy gate | Result |
|---|---:|
| Source fidelity | **120,000 / 120,000** |
| Exact surface lookup | **154,918 / 154,918** |
| Ambiguous exact surfaces | **962, all candidates retained** |
| Containment precision | **20,000 / 20,000** |
| Sentence substring pollution | **0 errors in 20,000 cases** |
| Accuracy errors | **0** |

Details: [`docs/OPEN_LEXICON_ACCURACY.md`](docs/OPEN_LEXICON_ACCURACY.md)

### Provenance and licensing

Approved runtime lexicons are separated by data license:

```text
dictionaries/system/lexicon.d/
├── cc0/
├── apache-2.0/
├── cc-by-sa/
└── copyleft-other/
```

Every promoted record preserves the source dataset, source version, license, source ID, source URL, SHA-256, and attribution. The MIT license of the program code does not replace the licenses of imported dictionary data.

Private logs, unknown licenses, unreviewed records, unresolved collisions, and records without source evidence cannot enter public runtime packs.

### Transactional promotion

Promotion is dry-run by default. With `--apply --performance`, it writes license-separated packs and dictionary fragments, creates reviewed Gold cases and source manifests, updates public counts and versions, and runs the full validator, test, accuracy, offline, 20x-scale, and Astera latency contracts.

Any failure removes new files and restores every changed file byte-for-byte.

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
- Never auto-promote generated dictionary proposals.
- Never download dictionary data at runtime.
- Never auto-promote readings as orthographic aliases.

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

The call-through boundary includes persistent local stdio, decoding, precompiled output-schema validation, and delivery of the complete Meaning Graph, Task Graph, and Guard result. Cold start and index/schema compilation complete before readiness.

### Validation contract

CI validates:

- Python 3.10 and 3.12
- all four open-dictionary importer fixtures
- common lexicon schema round-trip
- JMdict entry identity and reading restrictions
- proposal source and license evidence
- review and conflict-resolution gates
- rejection of private-log promotion
- license-separated runtime packs
- runtime lexicon provenance
- all 120,000 generated records against the official JMdict source
- all exact lexical surfaces
- ambiguous exact-surface candidate retention
- 20,000 containment precision cases
- 20,000 sentence substring-pollution cases
- MCP stdio end-to-end behavior
- existing totals and Gold regression
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
python tools/lexicon_validator.py
python tools/validator.py
pytest
python scripts/benchmark.py --check
python scripts/performance_contract.py --check --max-ready-ms 10
python scripts/astera_latency_contract.py --check --target-ms 10 --hard-ms 50
python -m compileall -q src tools scripts tests
```

### Scope and limitations

This project does not claim human-level understanding of arbitrary Japanese. It deterministically structures meaning supported by versioned grammar, rules, dictionaries, and context, and fails closed when quotation, reference, scope, discourse, or pragmatic intent cannot be resolved safely.

The supply chain automates large-scale collection, conversion, review preparation, testing, and promotion. The 120k accuracy contract verifies lexical identity data; it does not claim semantic or pragmatic understanding of every imported word. Only reviewed entries with sufficient meaning, scope, provenance, and safety evidence are promoted into semantic dictionaries.

<!-- project-control-en:start -->
### Project ownership, brand, and governance

**This project was created and is maintained by Seigo Kato ([`@seigo-gace`](https://github.com/seigo-gace)).** Under [`GOVERNANCE.md`](GOVERNANCE.md), the Project Owner retains final authority over the official repository, roadmap, architecture, releases, contribution acceptance, and permissions to use Project Marks.

Program code is free to use, modify, and redistribute under the MIT License. The MIT License does not authorize a modified fork, product, service, package, account, or organization to present itself as official by using `Deterministic Japanese Parser MCP`, `DJPMCP`, `Shiori MCP Server`, official logos, `Astera`, or other Project Marks. Brand use is governed by [`TRADEMARK.md`](TRADEMARK.md).

External contributions require DCO sign-off. Substantive code, dictionary, Gold, design, release, security, or governance contributions require a Project-Owner-accepted [`CONTRIBUTOR_LICENSE_AGREEMENT.md`](CONTRIBUTOR_LICENSE_AGREEMENT.md) before merge. See [`CONTRIBUTING.md`](CONTRIBUTING.md).
<!-- project-control-en:end -->

### License

Program code is MIT licensed. See [`LICENSE`](LICENSE) and [`NOTICE.md`](NOTICE.md).

Promoted external dictionary data remains governed by the source licenses recorded on each record and under `dictionaries/sources/`.
