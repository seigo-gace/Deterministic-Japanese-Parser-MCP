# 利用者追加Data Pack

Downloadした利用者が独自の組織語・業界語・製品語・専門表現を追加するための入口です。

YAML・JSON・JSONLをこのDirectory以下へ配置し、公式Dataと同じ共通Pipelineで次を行います。

- Unicode正規化
- 読み・品詞・語形の整理
- 表記揺れと検索索引の生成
- 意味候補・文脈条件・Parameterの構造化
- 重複・同形異義・既存Data衝突の検出
- Source・Version・License・Digestの検証
- Review Queue生成
- 承認済みDataだけのRuntime Compile
- Meaning Graphへの反映

利用者Dataは公式Dataを黙って上書きしません。同じSurfaceがある場合は候補を保持し、意味と文脈の根拠で判定します。ActionまたはSocial解釈が曖昧な場合はFail Closedします。

未承認DataはRuntimeと配布Wheelへ入りません。

詳細は `docs/UNIFIED_SEMANTIC_DATA_PIPELINE.md` を参照してください。
