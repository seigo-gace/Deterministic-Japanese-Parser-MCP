# Open Lexicon Accuracy Contract

## 1. 目的

このContractは、Open Lexiconが「12万件ある」と表示されるだけでなく、次をReleaseごとに確認するためのものです。

- Repository内のSource Snapshotが正確に120,000件ある
- 12分割されたSourceから、同じ120,000件のRuntime Dataを再構築できる
- 全RecordがSurface、Reading、Record LocatorのIndexへ接続されている
- ParserEngineが分割Fileを一つの辞書として読み込む
- 多義語を一件へ潰さない
- 語彙情報をIntent、Task、意味、外部操作へ勝手に昇格しない
- Offline配布物だけで起動できる

対象は語彙識別情報です。12万語すべての意味理解・語用理解・実行意図を保証するものではありません。

## 2. 「分割」の意味

12万件は、用途の違う二つの形でRepositoryへ置かれています。

### Source Snapshot

```text
dictionaries/system/lexicon.d/cc-by-sa/
├── release-...-0001.jsonl.gz  # 10,000件
├── ...
└── release-...-0012.jsonl.gz  # 10,000件
```

これは出典、License、加工前後の追跡、再構築のための正本です。

### Runtime Data

```text
dictionaries/system/compiled/open_lexicon/
├── manifest.json
├── indexes/
└── records/
    ├── records-0000.jsonl.gz  # 10,000件
    ├── ...
    └── records-0011.jsonl.gz  # 10,000件
```

これは高速検索のためにSource Snapshotから決定論的に作った実行用Dataです。

Fileが12個に分かれていても、Runtimeでは一つの辞書として扱います。起動準備中に全12Fileを読み込み、合計が120,000件でなければ起動を成立させません。共通IndexとRecord Locatorが、表記・読み・Record IDを正しいRecordへ接続します。

## 3. 現在のRepository Snapshot

現在の`main`に固定されているCompiled Manifestは次の内容です。

| 項目 | 現在値 |
|---|---:|
| Runtime Record | **120,000** |
| Sourceの実データShard | **12** |
| Runtime Record Shard | **12** |
| 1 Shardの基準件数 | **10,000** |
| Unique Lemma | **119,092** |
| Unique Exact Surface | **154,921** |
| Unique Reading | **126,936** |
| 同じSurfaceに複数Recordがある件数 | **1,711** |
| Part-of-speech Key | **70** |
| Domain Key | **93** |
| Usage-label Key | **46** |
| Record Locator Coverage | **120,000 / 120,000** |
| Runtime Lookup方式 | **Compiled Index** |

Source Datasetは`JMdict`、現在の固定Source Versionは`sha256-6de18f9e1bcb`、Source Licenseは`CC-BY-SA-4.0`です。

## 4. 現在のRelease Gate

### Source Snapshot Gate

全120,000 Recordについて次を検査します。

- `record_id`と`lemma`の存在
- Record IDの重複がないこと
- `review_status=approved`
- Dataset、Version、License、Source ID、Source SHA-256の存在
- 意味、Synonym、Intent、Taskなどの未承認Fieldが混入していないこと
- 12個の実データShardの合計が120,000件であること

### Deterministic Rebuild Gate

Repositoryの12 Source ShardからRuntime Dataを一時Directoryへ再構築します。

- Expected Record：120,000
- Runtime Record Shard：12
- 全IndexとRecord Fileを再生成
- Checked-in Runtime DataとFile単位で比較
- 差分が一つでもあれば失敗

### Full Index Coverage Gate

全120,000 Runtime Recordについて次を確認します。

- Record Locatorに存在する
- Exact Surface Indexに存在する
- Reading MappingがReading Indexに存在する
- Canonical Groupと表記が一致する
- Homograph IndexがSurface Indexの複数候補集合と一致する

### Runtime Integration Gate

ParserEngineを実際に起動し、次を確認します。

- `lookup_backend=compiled-index`
- `record_count=120000`
- Runtimeが利用可能
- 全12 Runtime Shardを起動準備中に読込済み
- Preload後の合計が120,000件
- 実入力からLexical CandidateとMeaning GraphのLexical Nodeが生成される

### Offline Wheel Gate

Release WheelをRepository外へOffline Installし、同じ120,000件のCompiled Runtimeを使って起動できることを確認します。

Release Wheelには実行に必要なCompiled Runtimeだけを入れます。再構築用Source SnapshotはRepositoryに残し、配布物へ同じ12万件を二重収録しません。

## 5. 安全境界

- Exact lexical lookupを基本とする
- Readingを表記Aliasへ自動昇格しない
- 同じSurfaceの複数候補を保持する
- Open LexiconをReviewed Synonym Trieへ混ぜない
- 語義を自動確定しない
- Intent、Task、Metaphor、Pragmatics、External Actionへ自動昇格しない
- Candidateが競合する場合は曖昧なまま保持する
- 5,000件のContext Candidate Registryは、承認されるまでRuntime判断に使わない

## 6. 旧検証値との区別

2026-08-04の旧Snapshotでは、次の値が記録されていました。

- Unique Exact Surface：154,918
- 同形異義Surface：962
- Source SHA-256：`9a46dadf...`

これらは当時のSnapshotに対する履歴であり、現在の`main`のCompiled Manifest値ではありません。

現在値は、2026-08-05に統合された120,000 Record Runtime Manifestの値である154,921 Surface、1,711 Homograph Surfaceです。公開READMEと検証文書は現在値へ統一します。

## 7. 実行Command

```bash
python tools/lexicon_validator.py
python tools/validate_compiled_open_lexicon.py \
  --root dictionaries/system/compiled/open_lexicon \
  --expected-records 120000
pytest \
  tests/test_compiled_open_lexicon.py \
  tests/test_open_lexicon_runtime.py \
  tests/test_lexical_meaning_graph.py \
  tests/test_repository_lexicon_integration.py \
  tests/test_workflow_safety_contract.py
```

Releaseは、件数、再構築一致、全Index接続、Runtime統合、Offline Install、安全境界、回帰、性能のどれか一つでも失敗した場合は成立しません。
