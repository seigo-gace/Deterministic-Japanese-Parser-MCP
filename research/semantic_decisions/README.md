# Semantic Decision Ledger

GPTアプリ上で利用者が指示し、内容を検討した結果は`decision_ledger.jsonl`へ保存します。
PipelineやGitHub Actionsが意味・極性・強度・用例を自動生成または自動承認することはありません。

12万件と5,000件は区別せず、同じ125,000件のReview Queueとして処理します。1行は1つのRecord・1つの承認Scopeに対する判断です。`semantic`には極性と0.0〜1.0の強度、`pragmatic`には必須／除外Context、`task`にはTask候補、`external_action`にはRiskの真偽を記録します。12万件のJMdict意味候補は上書きしません。必須項目は
`schemas/semantic_decision_ledger.schema.json`を参照してください。`input_sha256`が現在の入力Recordと一致しない古い判断は拒否されます。

Review対象は`reports/unified-semantic-data/review-batches/`に最大20件ずつ生成されます。
GPTアプリはReview Batchを読み、利用者の指示に従って`decision_ledger.jsonl`へ追記し、PR上で再実行します。

LLM API、API Key、Provider設定は現在の実装には置きません。将来追加する場合もDecision Ledgerを出力する外部Adapterとして扱い、Pipelineの決定論的な検査・承認境界は変更しません。
