# Open Lexicon Accuracy Contract

## 1. 目的

このContractは、Open Lexiconの件数、読込成功、速度だけではなく、取得元と加工後辞書の一致、完全一致検索の再現率、包含語・部分文字列による誤一致をReleaseごとに検証する。

対象は語彙識別情報である。語義、Intent、Task、Metaphor、Pragmatics、External Actionの意味精度を、このContractだけで保証するものではない。

## 2. 発見した旧構造の欠陥

旧12万語Snapshotでは、同じJMdict Entryの全表記と全読みを、各表記RecordへCross Productで登録していた。さらに、読みをCanonical Surfaceへ混ぜ、Canonicalizerが日本語文中の任意部分文字列を検索していた。

その結果、旧Snapshotでは次の入力だけで無関係なCanonical候補が発生した。

```text
UIは維持する。APIだけ変更しろ。 → 73件
これはテストです。                  → 38件
公園を確認する。                    → 30件
```

搭載件数と速度は条件を満たしていたが、語彙認識のPrecisionを満たしていなかった。

## 3. 修正した不変条件

- JMdictの1 Entryを1 Source-traceable Recordとして保持する。
- `keb`を表記として保持し、`reb`を読みMetadataとして分離する。
- `re_restr`と`re_nokanji`を`reading_mappings`へ保持する。
- 読みをOrthographic AliasまたはCanonical Synonymへ自動昇格しない。
- Open Lexiconは`exact_only_groups`として扱う。
- Projectが意味・用法をReviewしたSynonymだけが文中Trie検索の対象になる。
- 異なる完全一致語を、片方の文字列がもう片方へ含まれるという理由だけで同一視しない。
- 語義、Synonym Sense、Intent、Task、Metaphor、Pragmatics、External ActionはBase Lexiconへ自動昇格しない。

## 4. Release Accuracy Gate

Release Readinessは公式JMdict Dumpと、加工後のRuntime Packを独立経路で照合する。

### Source Fidelity

加工後の全Recordについて次を照合する。

- Source Entry ID
- Source SHA-256
- Lemma
- Orthographic Surface
- Reading
- Reading Restriction
- No-kanji Reading Flag
- Part of Speech
- Domain
- Usage Label
- Review Status
- Semantic Field非混入

### Exact Recall

加工後の全Surfaceを単独入力し、期待するCanonical候補集合と完全一致することを検証する。同形異義Surfaceは候補を一件へ潰さず、Sourceに存在する全候補を保持する。

### Precision

- 別語である短い語と長い包含語を20,000組検証する。
- Open Lexicon Surfaceを通常文へ埋め込んだ20,000文で、Exact-only語彙が文中部分一致として漏れないことを検証する。
- Project-authored Synonymの文中検索機能は維持する。

## 5. 2026-08-04 検証結果

Source：公式JMdict

```text
Source SHA-256
9a46dadf9e2df7500222fc6024045e2252946102a2c4a29a2ca7228f986e57e6
```

| 検証項目 | 結果 |
|---|---:|
| Runtime Record | 120,000 / 120,000 一致 |
| Source Record発見 | 120,000 / 120,000 |
| Source Fidelity | 120,000 / 120,000 |
| Unique Exact Surface | 154,918 |
| Exact Surface Lookup | 154,918 / 154,918 |
| 同形異義Surface | 962、全候補保持 |
| 包含語Precision | 20,000 / 20,000 |
| 文中部分一致汚染 | 20,000 / 20,000で発生0 |
| Unique Canonical Lemma | 119,092 |
| 正規化した重複Reading Element | 1 |
| Accuracy Error | 0 |

JMdict内に完全に同一のReading Elementが一件だけ重複していた。Schemaの決定論的重複除去と同じ方法で一件へ正規化し、意味・制約・表記の情報損失がないことを確認した。

## 6. 回帰・Offline・安全性

Accuracy修正済み12万語Wheelで次を再検証した。

- 452 Metaphor
- 339 Rule
- 649 Gold Case
- pytest 74件
- Python 3.10／3.12
- Repository外Offline Install
- Runtime Network Downloadなし
- Indexed／Exhaustive意味同値
- External Action Fail Closed
- 20倍辞書：6,780 Rule／9,040 Metaphor
- compileall

## 7. 性能

精度修正済み12万語Snapshotでの実測。

| 境界 | 実測 |
|---|---:|
| Astera常駐stdio初回 | 4.196ms |
| Astera常駐stdio p95 | 3.509ms |
| Astera常駐stdio最大 | 3.588ms |
| Kernel複合文 p95 | 1.561ms |
| 20倍辞書複合文 p95 | 2.361ms |
| 2万文字Rule Index p95 | 1.105ms |
| 2万文字Metaphor Index p95 | 1.117ms |

保証対象は`LowLatencyClientSession`による常駐local stdio境界である。Upstream MCP ClientのDiagnostic計測は約91msであり、保証経路として扱わない。

## 8. 実行Command

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

ReleaseはこのAccuracy Gate、既存回帰、Offline Wheel、性能契約の一つでも失敗した場合は成立しない。
