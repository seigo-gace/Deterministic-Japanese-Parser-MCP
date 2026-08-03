# Dictionary Supply Tools

これらは一回限りの補助Scriptではありません。無料・機械可読の日本語辞書資源、実利用Log、既存System辞書を接続し、候補収集から審査済み昇格までを反復実行する辞書Supply Chainです。

RuntimeはNetworkへ接続しません。DownloadとImportはBuild／更新作業時だけ行い、承認済みSnapshotをOffline Wheelへ同梱します。

## Source

| Source | 主な内容 | Runtime Pack License |
|---|---|---|
| Japanese Wiktionary | 日本語語釈、品詞、類義語、関連語、活用候補 | CC BY-SA / GFDL |
| Wikidata Lexemes | Lemma、Form、Sense、語彙Category、構造化関係 | CC0 |
| JMdict | 表記、読み、品詞、分野、用法、Cross Reference | CC BY-SA |
| SudachiDict source CSV | 表記、読み、品詞、正規化形 | Apache 2.0 |
| Masked unresolved logs | 実利用上の不足候補 | Review専用。公開Packへ昇格禁止 |

SourceごとにLicense Packを分離し、Source ID、Version、URL、SHA-256、AttributionをRecordへ保存します。

## 1. 公式Dumpを取得

```bash
python tools/fetch_open_dictionary.py \
  --source jawiktionary \
  --output downloads/jawiktionary.xml.bz2

python tools/fetch_open_dictionary.py \
  --source wikidata-lexemes \
  --output downloads/wikidata-lexemes.json.bz2

python tools/fetch_open_dictionary.py \
  --source jmdict \
  --output downloads/JMdict_e.gz
```

Downloadは一時Fileへ書き込み、完了後に原子的に置換します。SHA-256とHTTP Evidenceを隣接Manifestへ保存します。

## 2. 共通Lexicon SchemaへImport

```bash
python tools/dictionary_supply/importers/wiktionary.py \
  --input downloads/jawiktionary.xml.bz2 \
  --source-version 2026-08 \
  --output work/jawiktionary.jsonl

python tools/dictionary_supply/importers/wikidata_lexemes.py \
  --input downloads/wikidata-lexemes.json.bz2 \
  --source-version 2026-08 \
  --output work/wikidata-lexemes.jsonl

python tools/dictionary_supply/importers/jmdict.py \
  --input downloads/JMdict_e.gz \
  --source-version 2026-08 \
  --output work/jmdict.jsonl

python tools/dictionary_supply/importers/sudachi_csv.py \
  --input downloads/sudachi-system.csv \
  --source-version 20260428 \
  --output work/sudachi.jsonl
```

共通Recordには次を保持します。

- Lemma、Surface、Reading
- 品詞、Lexical Category、Form
- Sense、Domain、Usage Label
- Synonym、Antonym、Related
- Source Dataset、Version、License、Source ID、URL、SHA-256
- Review Status

## 3. 不足候補を収集

```bash
python tools/learner.py \
  --lexicon work/jawiktionary.jsonl \
  --lexicon work/wikidata-lexemes.jsonl \
  --lexicon work/jmdict.jsonl \
  --lexicon work/sudachi.jsonl \
  --log logs/parser.jsonl \
  --batch-id 2026-08-open-lexicon \
  --out proposals/2026-08-open-lexicon.yaml
```

既存Metaphor Surface、Rule Pattern、Canonical Surfaceとの衝突をProposalへ記録します。候補は自動採用されません。

## 4. Alias・FormをSense安全に補強

```bash
python tools/expander.py \
  --bundle proposals/2026-08-open-lexicon.yaml \
  --lexicon work/jawiktionary.jsonl \
  --lexicon work/wikidata-lexemes.jsonl \
  --out proposals/2026-08-open-lexicon-expanded.yaml
```

複数Recordが所有するSurfaceは曖昧候補として分離し、自動で同義語へ入れません。

## 5. Gold候補を作成

```bash
python tools/gold_generator.py \
  --bundle proposals/2026-08-open-lexicon-expanded.yaml \
  --out proposals/2026-08-open-lexicon-gold.json
```

RuleとMetaphorについて、肯定、否定、引用、疑問、External Action Guard候補を生成します。生成直後は`requires_review=true`です。

## 6. Review

Review Decision例：

```yaml
decisions:
  - proposal_id: PROP-METAPHOR-xxxxxxxxxxxxxxxxxxxx
    status: approved
    notes:
      - 実用例と文字通りの用法を確認済み
    positive_examples:
      - text: 障害対応では先に火消しをする。
        expected:
          metaphors: [火消し]
    negative_examples:
      - text: 消防隊が火事の火消しをした。
        expected:
          metaphors: []
    conflict_resolution: 既存EntryとはDomainを分離した
```

```bash
python tools/reviewer.py \
  --bundle proposals/2026-08-open-lexicon-expanded.yaml \
  --decisions reviews/2026-08-open-lexicon.yaml \
  --require-all-decided \
  --out reviewed/2026-08-open-lexicon.yaml
```

ConflictがあるProposalには`conflict_resolution`が必要です。Rule承認には肯定例、否定例、`external_action_reviewed: true`が必要です。

## 7. Promotion Dry Run

```bash
python tools/promoter.py \
  --bundle reviewed/2026-08-open-lexicon.yaml \
  --batch-id 2026-08-open-lexicon
```

書き込むFile一覧だけを表示します。

## 8. Transactional Promotion

```bash
python tools/promoter.py \
  --bundle reviewed/2026-08-open-lexicon.yaml \
  --batch-id 2026-08-open-lexicon \
  --apply \
  --performance
```

次を行います。

1. License別Lexicon Packへ書き込み
2. Metaphor／Rule／Synonym Fragmentへ書き込み
3. Review済みGoldへ書き込み
4. Source Manifest作成
5. Manifest件数更新
6. README件数更新
7. Dictionary Version更新
8. Validator、pytest、compileall実行
9. 20倍辞書、Astera 10ms／50ms性能Contract実行
10. 一件でも失敗した場合は全FileをRollback

## Validation

```bash
python tools/lexicon_validator.py
python tools/validator.py
pytest
```

Runtime Lexiconは`review_status=approved`だけを読みます。Private Log、License不明、Source ID欠落、未承認Recordは強制失敗します。
