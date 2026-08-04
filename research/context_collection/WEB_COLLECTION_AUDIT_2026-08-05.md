# Web収集監査・Context Data拡張 v2 — 2026-08-05

## 訂正結論

前回v1の29 Source・328 Entryだけでなく、本v2の115 Source・1,145 Surface Candidateも、依頼された「まとめサイト、専門辞書、収集サイトを徹底的に回る」収集量としては不足している。

1,145件で止まった原因は、候補発見と意味審査を混同し、Evidenceが不足する語を候補Queueへ残さず収集段階で落としたこと、一覧PageのPagination・下位Category・公開Dataset本体を全件展開しなかったこと、Source Record数を実収集件数の代わりに扱ったことにある。

**v2を収集完了とは扱わない。現在StatusはUNDER_COLLECTED。重複正規化後の新規Surface Candidateを最低5,000件、収集時の取りこぼしを考慮した内部目標を6,000件以上とする。**

## 現在値と不足

- Source Registry: 115 Source Record / 52 Unique Domain
- 既存の意味・Context・Test付きSeed: 328 Entry
- 新規Surface Candidate: 1,145件
- 最低収集条件までの不足: 3,855件
- 内部目標6,000件までの不足: 4,855件
- 新規Candidateの意味確定: 0件
- 現在判定: `UNDER_COLLECTED`

## 5,000件が妥当な根拠

公開されている主要Sourceだけでも、個別の候補母数は次の規模を持つ。

- Wiktionary English edition Japanese slang: 約818 Entry
- Wiktionary English edition Japanese internet slang: 約484 Entry
- Wiktionary English edition Japanese onomatopoeia: 約467 Entry
- Wiktionary Japanese edition 日本語俗語: 約832 Page
- Wiktionary Japanese edition 日本語オノマトペ: 約359 Page
- Ono.Jepang.org: 1,295 Onomatopoeia Entry
- Kaikki Japanese senses tagged slang: 約910 Sense
- Kaikki Japanese senses tagged informal: 約789 Sense
- Kaikki Japanese senses tagged idiomatic: 約760 Sense

上記には重複があるが、さらにInterjection、Phrase、Proverb、Discourse、Honorific、Dialect、Game、Streaming、Fandom、Reference、Modalityを加えるため、重複除去後5,000件は過大要求ではない。

## 修正した収集構造

### Stage A: Candidate Discovery

意味・極性・現役性が未確定でも、表記と発見Sourceが確認できれば`needs-evidence`へ残す。Candidate発見段階で捨てない。

### Stage B: Evidence Enrichment

読み、別表記、意味候補、極性、強度、対象、Domain、世代、Community、使用時期、必須Context、除外Contextを付ける。

### Stage C: Safety and Tests

Positive / Negative / Boundary / 引用 / 否定 / 疑問 / 仮定 / 伝聞 / External Action Riskを作る。

### Stage D: Promotion

License、Snapshot SHA-256、複数Evidence、Review、Independent Holdoutが揃ったEntryだけを`approved`へ昇格する。

## 構造

- `reviewed_seed_v1.jsonl`: 前回の意味・Context・Test付き328 Entry。v2で再審査済みとは扱わない。
- `expansion_queue_v2.jsonl`: 新規Surface候補。意味は`not-asserted`、Statusは全件`needs-evidence`。
- `source_registry_v2.*`: 辞書、Corpus、まとめサイト、専門辞書、調査、研究、公式Help、Licenseを統合したSource台帳。
- `coverage_matrix.csv`: Source数、新規Candidate数、既存Seed数をFeature別に可視化。

## Source分類

1. Raw同梱可能: CC0、CC BY、CC BY-SA、Apache、選択Licenseを固定できるData。
2. 派生Featureのみ: 研究論文、検索型Corpus、契約Corpus。
3. Evidenceのみ: 商用辞書、出版社の語釈、公式Help、調査Report。
4. Candidate発見のみ: まとめサイト、Community用語集、License不明Collection。
5. Restricted/Reject: SNS本文、大量Corpus原文、Private Log、出典不明一覧。

## 重要な安全条件

- まとめサイト掲載だけで意味、極性、現役判定を確定しない。
- 新規Candidateは直接出現Source＋独立した意味/Context Sourceが揃うまでApprovedへ上げない。
- 命令、否定、引用、参照候補はScope解決前にExternal ActionをBLOCKする。
- Corpus本文や商用辞書の語釈・用例をRepositoryへ転載しない。
- Surveyは母集団、調査時期、認知と実使用を分離する。

## 現在の検証範囲

```json
{
  "sources": 115,
  "queue": 1145,
  "errors": [],
  "collection_status": "UNDER_COLLECTED",
  "minimum_unique_candidate_target": 5000,
  "internal_discovery_target": 6000
}
```

`errors=[]`は既存1,145件の台帳構造にErrorがないという意味に限る。収集量、意味精度、Web網羅性の合格を意味しない。

## 未完了

- 重複正規化後5,000件以上のCandidate収集。
- 各一覧のPagination・下位Category全展開。
- 各Candidateの直接出現確認と引用位置の固定。
- Source Snapshot取得とSHA-256固定。
- Sudachi 20260428→20260723のEntry単位差分。
- Candidateごとの読み、意味候補、極性、Domain、Positive/Negative/Boundary Test作成。
- 複数Reviewer一致度とHoldout分離。
