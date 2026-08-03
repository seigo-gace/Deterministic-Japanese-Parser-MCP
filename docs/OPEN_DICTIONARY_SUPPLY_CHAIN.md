# Open Dictionary Supply Chain

## 1. 目的

`learner.py`、`expander.py`、`gold_generator.py`は、候補Fileを出すだけの骨格ではなく、無料・機械可読の日本語辞書資源と実利用Logを、Deterministic Japanese Parser MCPの現行辞書構造へ安全に追加するための反復可能なSupply Chainとして完成させる。

この仕組みは辞書追加を避けるものではない。大量の語彙、語義、表記揺れ、活用、慣用句、現代語を継続的に増やしながら、無審査採用、License混在、誤検出、External Action誤許可を防ぐ。

## 2. 採用Source

### Japanese Wiktionary

用途：日本語語釈、品詞、語源、類義語、対義語、関連語、複合語、活用候補。

Import形式：公式`pages-articles.xml.bz2` Dump。

License Pack：`cc-by-sa`。

注意：Wikitextを解析し、日本語Sectionだけを抽出する。TemplateやLink表記を除去しても、Source Revision ID、URL、Dump SHA-256を保持する。

### Wikidata Lexemes

用途：Lemma、Form、Sense、Lexical Category、Grammatical Feature、Sense関係。

Import形式：公式`latest-lexemes.json.bz2` Dump。

License Pack：`cc0`。

注意：Japanese Language Item `Q5287`だけを抽出する。Lexeme ID、Form ID、Sense IDを失わない。

### JMdict

用途：表記、読み、品詞、分野、用法、Dialect、Cross Reference、Antonym、多言語Gloss。

Import形式：公式`JMdict_e.gz`。

License Pack：`cc-by-sa`。

注意：JMdictの英語Glossだけを日本語語釈として扱わない。日本語Senseの補助Evidenceとして保持し、Meaning／Intent昇格時は日本語SourceまたはReviewを必須にする。

### SudachiDict Source CSV

用途：Surface、Reading、品詞、活用情報、Normalized Form。

Import形式：Source CSV。

License Pack：`apache-2.0`。

注意：Sudachiの語彙情報を、慣用表現の意味定義へ勝手に変換しない。表記・読み・品詞・正規化の基盤として使う。

### Masked Runtime Logs

用途：実利用上の未対応表現、誤解析、曖昧性、Unsupported候補の収集。

License Pack：なし。`PRIVATE-REVIEW-ONLY`。

注意：公開Runtime Packへの直接昇格を禁止する。秘密情報Mask後でも、入力文をそのまま公開しない。別Sourceで意味と用法を確認し、新しい独自Entryとして審査する。

## 3. 共通Lexicon Schema

全Sourceを次へ統一する。

```json
{
  "schema_version": "1.0.0",
  "record_id": "...",
  "lemma": "...",
  "language": "ja",
  "readings": [],
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

同一LemmaでもReadingまたはSenseが異なる場合は一つへ潰さない。Mergeは`lemma + readings`を基礎Keyとし、Source Record IDをNotesへ残す。

## 4. Processing Flow

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
    ├─ Existing Metaphor Surface collision
    ├─ Existing Rule Pattern collision
    ├─ Existing Canonical Surface collision
    └─ Source / License evidence
    ↓
Proposal Bundle
    ↓
expander.py
    ├─ Surface / Form expansion
    ├─ Alias candidates
    └─ Ambiguous surface separation
    ↓
gold_generator.py
    ├─ Positive
    ├─ Negative
    ├─ Quote
    ├─ Question
    └─ External Action Guard candidates
    ↓
reviewer.py
    ├─ Meaning confirmation
    ├─ Intent confirmation
    ├─ Conflict resolution
    ├─ Positive / Negative examples
    └─ External Action review
    ↓
promoter.py --apply --performance
    ├─ License-separated runtime packs
    ├─ Metaphor / Rule / Synonym fragments
    ├─ Reviewed Gold
    ├─ Source Manifest
    ├─ README / Manifest / Version sync
    ├─ Validator / pytest / compileall
    ├─ 20x dictionary performance
    ├─ Astera 10ms / 50ms contract
    └─ Failure rollback
```

## 5. Review Contract

### Lexicon

- Lemmaが正しい。
- Source LicenseとAttributionが確認できる。
- SenseとFormがSourceの意味を変えていない。
- Public Packへ入れてよいSourceである。

### Synonym

- 同じSenseで相互交換可能である。
- 近義語、上位語、下位語、反義語をSynonymへ混ぜない。
- Multiple Sense Surfaceを一つのCanonicalへ固定しない。

### Metaphor／Pragmatic Expression

- 文字通りの用法と非文字通りの用法を区別する。
- 短い多義表現にはContext Gateを設定する。
- PositiveとLiteral Negativeの両方をGoldへ入れる。

### Rule

- Target CaptureとScopeを確認する。
- Quote、Question、Negation、HypotheticalでExternal Actionを誤許可しない。
- `external_action_reviewed: true`を必須にする。
- PositiveとNegativeを両方登録する。

## 6. License Separation

```text
dictionaries/system/lexicon.d/
├── cc0/
├── apache-2.0/
├── cc-by-sa/
└── copyleft-other/
```

MIT Codeと外部DataのLicenseを同一視しない。各RecordへSource Licenseを保存し、Pack単位でも分離する。Source ManifestにはBatch内の全Source、Version、License、Checksum、Attributionを記録する。

`PRIVATE-REVIEW-ONLY`とLicense不明Sourceは公開Packへ昇格できない。

## 7. Runtime Contract

- RuntimeはNetworkへ接続しない。
- Runtime Downloadを行わない。
- `review_status=approved`だけを読む。
- Lexicon Surfaceと承認済みSynonymをCanonicalizerへ統合する。
- 一つのSurfaceが複数Canonicalを持つ場合、衝突を隠さず候補集合として保持する。
- 大規模Pack追加後も10ms通常目標、50ms絶対上限を再検証する。

## 8. Promotion Transaction

Promotion対象File、Manifest、README、Versionを事前Backupする。書込後に全Validationを実行し、一件でも失敗した場合は新規Fileを削除し、既存FileをByte単位で復元する。

同じBatch IDの再実行で既存Fileを上書きしない。修正版は新しいBatch IDを使用する。

## 9. 完了条件

- [ ] 公式Dump DownloaderがSource Manifestを作る
- [ ] 4 ImporterのFixture Test成功
- [ ] 共通Schema Round Trip成功
- [ ] Existing Dictionary Collision検出成功
- [ ] Review Gate成功
- [ ] Private Log昇格拒否成功
- [ ] License別Pack分離成功
- [ ] Runtime Lexicon Provenance成功
- [ ] Existing 452 Metaphor／339 Rule／649 Gold回帰成功
- [ ] Python 3.10／3.12成功
- [ ] Offline WheelでLexicon Pack読込成功
- [ ] 20倍辞書性能成功
- [ ] Astera 10ms／50ms契約成功
