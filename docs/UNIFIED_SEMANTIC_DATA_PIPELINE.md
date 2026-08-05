# 汎用Semantic Data Supply・Runtime Integration Pipeline

## 結論

このPipelineは、12万件と5,000件だけを一度加工するScriptではありません。

Deterministic Japanese Parser MCPが日本語をMeaning Graphへ変換するために必要なDataを、一般語彙・文脈表現・専門分野・利用者追加Dataから同じSchemaへ加工し、Review・Compile・本体接続・Wheel配布まで一続きで行う基盤です。

## 本体との関係

本体の目的は辞書検索ではありません。

```text
日本語入力
  ↓
正規化・Token・読み・品詞・語形
  ↓
語彙と意味候補
  ↓
Clause・Proposition・Argument・Scope・Reference
  ↓
極性・強度・発話行為・敬語・語用・文脈
  ↓
Meaning Graph
  ↓
Action Task Graph・External Action Guard
```

本Pipelineは、このMeaning Graphへ根拠付きDataを供給します。

## 入力

標準入力：

- `dictionaries/system/lexicon.d/`：一般語彙の基礎Data
- `research/context_collection/expansion_v3/`：若者言葉、オノマトペ、敬語、談話、指示、省略等のContext候補
- `dictionaries/domain_packs/`：医療、物理、金融、経済、教育等の公式専門分野Pack
- `dictionaries/user_packs/`：Download利用者が追加するLocal Pack

対応形式：

- YAML
- JSON
- JSONL
- gzip JSONL

## 共通加工Schema

各Entryを次へ正規化します。

- Record ID
- 見出し語
- Surface・正規化Surface・表記揺れ
- 読み・読み制約
- 品詞
- 原形・Token別形態情報・活用情報
- Domain・Usage Label・Feature Type
- 複数のMeaning Candidate
- 極性・強度・Register・Parameter
- Context条件
- Positive・Negative・Boundary Example
- Semantic Target
- Risk Class
- Source・Version・License・Digest・Evidence Scope
- Review Status・Review Blocker
- 既存Runtime DataとのLink

入力に読み・品詞・語形が不足する場合は、固定VersionのSudachi Coreを使って候補を構造化します。

入力Sourceに意味・Interpretation・Senseがある場合は、複数Meaning Candidateとして保持します。Sourceに意味がない場合、定義を捏造せず未確定Candidate Shellを作り、`meaning-candidate-required`としてReview Queueへ送ります。

## 既存Dataとの統合

既存の高精度Dataを消したり置換したりしません。

- 比喩
- 類義語Group
- Language Feature
- Intent Rule
- Task Template
- Gold Case

新規RecordのSurfaceを既存Dataと照合し、`existing-runtime-links.jsonl`へ接続候補を出力します。

`semantic_targets`は次を指定できます。

- `lexicon`
- `language_feature`
- `metaphor`
- `metonymy`
- `synonym`
- `intent_rule`
- `task_template`
- `gold_case`

すべての語をRuleやTaskへ変換するのではなく、意味と用途が合うTargetだけを指定します。

## Review Asset

```text
reports/unified-semantic-data/
├── manifest.json
├── review-records.jsonl
├── review-queue.jsonl
├── runtime-candidates.jsonl
├── collision-report.jsonl
└── existing-runtime-links.jsonl
```

Review Queueには次が残ります。

- 意味候補不足
- 読み・品詞不足
- Source・Version・License・Digest不足
- 未承認Candidate
- Positive・Negative・Boundary不足
- Context・Action・Social判断が必要なもの

機械的に確定できない意味・極性・強度・用例だけをReviewerが確認します。

## 承認済みCompile

`review_status=approved`かつReview Blockerが0件のRecordだけをCompileします。

生成Index：

- Surface Index
- Reading Index
- Lemma Index
- POS Index
- Domain Index
- Meaning Candidate Index
- Semantic Target Index
- Record Locator
- gzip Record Shard
- Manifest・SHA-256

同じSurfaceに複数の意味がある場合は候補を削除せず保持します。

## 本体Runtime接続

`SemanticDataRuntime`が承認済みCompiled Packだけを読みます。

本体解析後、Tokenと命題Spanを照合し、Meaning Candidateを決定論的に順位付けして次へ反映します。

- `Proposition.sense_id`
- `sense_label`
- `sense_confidence`
- `sense_candidates`
- `polarity`
- `force_level`
- `directness`
- `politeness_level`
- `speech_act`
- `epistemic_status`
- `register_labels`
- `honorific_classes`
- `interaction_functions`
- `information_territory`
- `sensory_features`
- `MeaningGraph.language_features`

その後、Action Task GraphとExternal Action Guardを再評価します。

ActionまたはSocialに関わる意味候補が絞れない場合は、命題を`AMBIGUOUS`にし、`executable_candidate=false`としてFail Closedします。

Compiled Packから外部操作を自動生成することは禁止します。

## 専門分野Series

医療・物理・金融・経済・教育等を別々の仕組みで実装しません。

分野Dataを`dictionaries/domain_packs/<domain>/`へ追加し、同じ加工・Review・Compile・Runtime接続を使います。

専門分野Dataは単なる用語集ではなく、分野別のMeaning Candidate、Domain、Context条件、否定・疑問・仮定、強度、RelationをMeaning Graphへ供給する読解能力Packとして扱います。

## 利用者追加Pack

利用者Dataも同じSchemaで検証します。

同じSurfaceが公式Dataに存在しても黙って上書きしません。候補を併存させ、Domain・Context・POS・Evidenceで選択します。根拠が不足すれば曖昧なまま返します。

## 実行

```bash
python tools/unified_semantic_data_pipeline.py --compile-approved
```

Byte Determinism確認：

```bash
python tools/unified_semantic_data_pipeline.py --check
```

## GitHub Actions

`.github/workflows/unified-semantic-data.yml`は次を実行します。

1. 12万件・5,000件・Domain Pack・User Packを全件読込
2. 共通Schema加工
3. Review Queue・衝突・既存Data Link生成
4. 承認済みDataだけCompile
5. 二回再構築のByte一致
6. Meaning Graph統合Test
7. 既存Gold・Holdout・Safety Contract
8. 10ms Target・50ms Hard Limit
9. Wheel Build
10. Repository外InstallとRuntime解析
11. Evidence Artifact保存

WorkflowはRepositoryへCommit・Pushしません。

## 安全境界

- 意味・定義を捏造しない
- 自動承認しない
- 未承認DataをRuntimeへ入れない
- 不明LicenseをRuntimeへ入れない
- 同形異義語を一つへ潰さない
- 利用者Dataで公式Dataを黙って上書きしない
- Meaning CandidateからIntent・Task・External Actionを無条件生成しない
- Action／Socialの曖昧性はFail Closedする
- Meaning Graphを唯一の意味正本とする
