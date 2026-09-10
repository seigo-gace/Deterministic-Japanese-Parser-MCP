# 専門分野Data Pack

このDirectoryは、医療・物理・金融・経済・教育などの専門分野Dataを、Deterministic Japanese Parser MCPの共通Semantic Data Pipelineへ投入する入口です。

分野ごとにSubdirectoryを作り、YAML・JSON・JSONLを配置します。

```text
dictionaries/domain_packs/
├── medicine/
├── physics/
├── finance/
├── economics/
└── education/
```

最低限必要な情報：

- `record_id`
- `lemma`または`surface`
- `surfaces`
- `readings`
- `part_of_speech`
- `domains`
- `meaning_candidates`
- `semantic_targets`
- `source.dataset`
- `source.version`
- `source.license`
- `source.source_sha256`
- `approval_scopes`（`lexical`、`semantic`、`pragmatic`、`task`、`external_action`）

Language Featureへ反映するEntryは、Positive・Negative・Boundary Exampleも必要です。

未承認Dataや、意味・Source・Licenseが不足するDataはReview Queueへ送られます。GPTアプリで内容を確認してDecision Ledgerを作成し、承認済みScopeだけをCompileします。Pipeline内でLLM APIを呼んだり、自動承認したりはしません。

詳細は `docs/UNIFIED_SEMANTIC_DATA_PIPELINE.md` を参照してください。
