# Web収集監査・Context Data拡張 v2 — 2026-08-05

## 結論

前回v1は29 Source・328 Entryに留まり、「まとめサイト、専門辞書、収集サイトを徹底的に回った」と表現できる状態ではなかった。本v2では、既存Seedを維持したまま、Source棚卸しを **115 Source** へ拡張し、未検証の意味を捏造しない **1145 Surface Candidate** を別Queueへ追加した。

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

## 検証

ローカルCollection Validator結果:

```json
{
  "sources": 115,
  "queue": 1145,
  "errors": []
}
```

## 未完了

- 各Candidateの直接出現確認と引用位置の固定。
- Source Snapshot取得とSHA-256固定。
- Sudachi 20260428→20260723のEntry単位差分。
- Candidateごとの読み、意味候補、極性、Domain、Positive/Negative/Boundary Test作成。
- 複数Reviewer一致度とHoldout分離。
