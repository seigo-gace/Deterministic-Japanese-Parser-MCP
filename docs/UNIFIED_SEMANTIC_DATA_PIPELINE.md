# 辞書データ自動加工・統合パイプライン

## 目的

この仕組みは辞書の意味をAIで大量生成するものではありません。Deterministic Japanese Parser MCPが利用するデータを、入力元が増えても同じ品質・安全・速度条件で受け入れられるようにする非AI・決定論的な供給基盤です。

対象は、JMdict意味候補を保持するオープン辞書120,000件、特殊・文脈語彙5,000件、将来の専門辞書、利用者追加データです。120,000件と5,000件は同じ共通Schema・同じReview Queue・同じDecision Ledgerで処理します。既存の比喩・判定規則・類義語Group・Task Template・Gold Caseは別レイヤーの正本として保持し、新規データから型付きRelationだけを生成します。

## 実行主体の境界

| 主体 | 行うこと | 行わないこと |
|---|---|---|
| GPTアプリ | 利用者の一括指示を受ける、125,000件のReview Batchを読む、Decision Ledgerを作る、PR結果を説明する | Runtime内推論、GitHub Actions内からのAPI推論、自動承認、JMdict意味候補の上書き |
| GitHub Actions + Python | Schema化、正規化、重複・衝突・Source・License検査、Ledger適用、承認Scope限定Compile、品質・安全・速度Gate | 意味の創作、判断の代行、BranchへのCommit・Push |
| MCP Runtime | Wheelに同梱された承認済みPackをオフラインで決定論的に参照する | 未承認候補の読込、外部API呼出し、辞書からの外部操作生成 |

現在の実装にLLM API Client、API Key、Provider Secret、Workflowからの推論呼出しはありません。LLM APIは将来、Decision Ledgerを作る外部Adapterとして追加できる境界だけを設計対象とし、現在は実装しません。

## 入力とAdapter

| 入力 | 入口 | 主用途 | 既定の判断境界 |
|---|---|---|---|
| オープン辞書120,000件 | `dictionaries/system/lexicon.d/` + checksum固定JMdict | Surface・読み・品詞・語形・出典・意味候補 | 5,000件と同じReview Queueへ送る。意味候補は保持する |
| 特殊語彙5,000件 | `research/context_collection/expansion_v3/` | Context由来候補と共通Schema項目 | 120,000件と同じReview Queueへ送る |
| 専門辞書 | `dictionaries/domain_packs/<domain>/` | 分野固有の意味・用法 | Coreと分離。明示承認後だけ統合参照 |
| 利用者データ | `dictionaries/user_packs/<pack>/` | 組織・製品・ローカル表現 | 公式Dataを上書きせず併存 |

入力形式はYAML、JSON、JSONL、gzip JSONLです。全Adapterは最終的に共通Recordへ変換されます。

## 共通Record

Schemaは`schemas/unified_semantic_record.schema.json`です。出力は次を保持します。

- Surface、正規化Surface、表記揺れ
- 読み、品詞、原形、語形・活用
- 意味候補、極性、強度
- 使用場面、Register、社会関係、文脈条件
- 肯定例、否定例、境界例
- Source、Version、License、Source ID、SHA-256、Attribution
- 分野、Semantic Target、Risk Class
- 既存Dataとの型付きRelation候補
- 入力RecordのSHA-256とDecision ID
- Scope別の承認状態とBlocker

Sudachi Coreは不足した読み・品詞・語形の機械的候補整理だけに使います。意味は生成しません。120,000件の意味候補は`research/semantic_sources/jmdict/source-lock.json`で固定したPR #26のWorkflow Artifactから復元し、Review判断で上書きしません。日次更新されるJMdict配布URLを毎回取り直す方式ではないため、処理途中に意味候補が変わりません。

## 承認Scope

承認はRecord全体の1つのBooleanではなく、次のScopeごとに管理します。

1. `lexical`：Surface・読み・品詞・語形
2. `semantic`：意味・分野・極性・強度
3. `pragmatic`：使用場面・社会関係・文脈・肯定／否定／境界例
4. `task`：Intent Rule・Task Templateとの関係
5. `external_action`：外部操作に関係する安全判断

Compilerは`lexical`が承認されたRecordだけを受け入れ、さらに未承認ScopeのFieldを削ってからPack化します。したがって、12万件の語彙同定を使いながら、未承認の意味や語用をRuntimeへ混入させません。

## Review BatchとDecision Ledger

判断が残るRecordは`reports/unified-semantic-data/review-batches/`へ最大20件ずつ分割します。GPTアプリはこのBatchを読み、利用者の指示に従って`research/semantic_decisions/`へDecision Ledgerを追加します。

Decision Ledgerの正本は`research/semantic_decisions/decision_ledger.jsonl`です。Record ID、Scope、判断、Reviewer、日時、理由、元入力RecordのSHA-256を必須とします。`semantic`判断は極性（positive / negative / neutral）と強度（0.0〜1.0）、`pragmatic`判断は必須／除外Context、`task`判断はTask候補、`external_action`判断はRiskのtrue / falseをPatchへ記録します。入力が変更されてSHA-256が一致しなくなった古い判断は適用しません。Ledger Schemaは`schemas/semantic_decision_ledger.schema.json`です。

120,000件と5,000件は一つのQueueへ入り、同じBatch生成規則で処理されます。Source種別による除外・優先処理は行いません。125,000件すべての必要Scopeが確定するまで公開Gateは開きません。

Pipeline自身は承認を作りません。Reviewが残る間、WorkflowはEvidenceを保存した後に`REVIEW_REQUIRED`で失敗し、公開可能状態にしません。

## 自動生成物

`reports/unified-semantic-data/`に次を生成します。

- `manifest.json`
- `review-records.jsonl`
- `review-queue.jsonl`
- `review-batches/`と`review-batch-index.jsonl`
- `approved-records.jsonl`
- `decision-audit.jsonl`
- `collision-report.jsonl`
- `license-report.jsonl`
- `source-manifest.jsonl`
- `existing-runtime-links.jsonl`

承認済みPackは`dictionaries/system/compiled/semantic_data/`にManifest、gzip Record Shard、Surface・Reading・Lemma・POS・Domain・Meaning・Target Indexとして出力します。同形異義は潰さず、候補を保持します。

Pack全体のIndexとは別に、Semantic Runtime専用のSurface・Reading・Record Locator Indexを生成します。Lexicalだけが承認済みのRecordはPackと全体Indexへ残しますが、承認済み意味候補がないためSemantic Runtime検索Indexには入れません。語彙同定はOpen Lexicon層、承認済み意味・語用の追加はSemantic Runtime層が担当し、同じLexical RecordのGzip Shardを意味解析のたびに重複読込しない構造です。

## 専門・利用者Packの分離

Core、専門、利用者の入力は物理的に別Directoryで管理し、正規化後も`pack_namespace`を保持します。衝突時に黙って上書きせず、`collision-report.jsonl`へ全Record IDを出します。Runtime利用時は有効にするDomain/User Packを選び、Coreとの候補集合として統合参照する設計です。

## GitHub Actions

`.github/workflows/data_pipeline.yml`は対象PRで次を実行します。

1. Run ID・Artifact ID・件数・SHA-256固定のPR #26 Review Queueを復元
2. 4種Adapterから125,000件と追加Packを共通Schemaへ正規化
3. Source・License・Digest、重複、同形異義、既存Data Relationを検査
4. 既存Decision Ledgerだけを適用
5. 125,000件の共通Review QueueからReview Batchを最大20件で生成
6. 承認ScopeだけをCompile
7. 2回BuildのByte一致を検査
8. Adapter・Review・Runtime Pack Test
9. Gold、Holdout、External Action Safety Gate
10. p95 10ms Target、50ms Hard Limit
11. Approved-only Wheel BuildとRepository外Offline Test
12. Evidence ArtifactとPR Summaryを保存
13. Review残件があれば`REVIEW_REQUIRED`で停止

Workflowの権限は`contents: read`のみで、Commit・Push・Merge・Releaseは行いません。

## 実行方法

```bash
python tools/unified_semantic_data_pipeline.py --compile-approved
python tools/unified_semantic_data_pipeline.py --check
python tools/unified_semantic_data_pipeline.py --require-review-complete
```

## 公開Gate

公開可能なのは、Review残件がなく、Byte Determinism、既存辞書検証、Gold、独立Holdout、外部操作安全性100%、Macro精度95%以上、各Category 90%以上、p95 10ms以下、Hard 50ms以下、Wheel Offline検証の全てが成功した場合だけです。いずれか1つでも失敗すれば公開処理を止めます。
