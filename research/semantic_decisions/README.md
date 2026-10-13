# Semantic Decision Ledger

GPTアプリ上で利用者が指示し、内容を検討した結果は`decision_ledger.jsonl`へ保存します。
PipelineやGitHub Actionsが意味・極性・強度・用例を自動生成または自動承認することはありません。

12万件と5,000件は区別せず、同じ125,000件のReview Queueとして処理します。1行は1つのRecord・1つの承認Scopeに対する判断です。`semantic`には極性と0.0〜1.0の強度、`pragmatic`には必須／除外Context、`task`にはTask候補、`external_action`にはRiskの真偽を記録します。12万件のJMdict意味候補は上書きしません。必須項目は
`schemas/semantic_decision_ledger.schema.json`を参照してください。`input_sha256`が現在の入力Recordと一致しない古い判断は拒否されます。

Review対象は`reports/unified-semantic-data/review-batches/`に最大20件ずつ生成されます。
GPTアプリはReview Batchを読み、利用者の指示に従って`decision_ledger.jsonl`へ追記し、PR上で再実行します。

LLM API、API Key、Provider設定は現在の実装には置きません。将来追加する場合もDecision Ledgerを出力する外部Adapterとして扱い、Pipelineの決定論的な検査・承認境界は変更しません。

## J-Ono source POS review (explicit lexical Decision only)

J-Ono Review Queueの `source-part-of-speech-required` は、形態解析器が返した暫定POSや表記・読み一致だけでは解除しません。単一語義Recordで、原典意味と独立参照先の**該当語義**・文脈を明示確認したときのみ、既存Decision Ledgerで次の操作を認めます。

- `scope="lexical"`、`status="approved"`、一致する `record_id` / `input_sha256`、追跡可能な `rationale` とReviewerを必要とする。
- `patch.part_of_speech` は空でない文字列配列。J-Ono原典Evidence `kind=j-ono-source-authored-review-evidence`、未解決の `source-part-of-speech-required`、単一意味候補のときだけ受理する。
- 適用時にRecord本体とその単一Meaning CandidateのPOSを同一値へ更新する。すべての原典意味・Evidence ID・Candidate IDは維持する。
- 複数語義、POS根拠不足、古いDigest、他Scope/Sourceではこの経路を使用しない。未承認を維持する。
- `lexical`と`semantic`の両承認および他のCanonical Dictionary条件が満たされるまでは製品Runtimeへ統合しない。

この処理は**Reviewerが明示的に決定する既存Ledger機構の補完**であり、自動POS推論・一括承認・第二の意味Authorityではありません。詳細なJ-Ono原典↔JMdict照合は同ディレクトリのreview-only evidence JSONに保存し、それだけでは承認になりません。
