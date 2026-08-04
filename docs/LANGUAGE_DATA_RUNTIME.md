# Language Data Runtime Contract

## 目的

収集した若者言葉、ネット語、オノマトペ、感覚表現、命令・依頼段階、敬語、ウチ／ソト、相槌、終助詞、情報のなわ張り、比喩・メトニミーを、単語一覧で終わらせず、Deterministic Japanese Parser MCPのMeaning Graphへ確実に反映する。

Runtimeは非AI・非生成・Offline・決定論的のままとし、Web検索、外部辞書取得、YAML解析、辞書Merge、語義生成、Index構築をユーザー要求の処理中に行わない。

## 受入Data

収集Entryは最低限、次を持つ。

- `entry_id`
- `feature_type`
- `surfaces`と`match_mode`
- 複数を保持できる`interpretations`
- `parameters`
- `register`
- `required_any` / `required_all` / `forbidden_any`
- `required_social` / `required_discourse`
- `fallback_status`
- `risk_class`
- `evidence`
- Review時のPositive / Negative / Boundary examples

外部Sourceの`evidence`は、次を必須とする。

- `dataset`
- `version`
- `license`
- `source_id`
- `source_url`
- `source_sha256`
- `evidence_scope`

`evidence_scope`は、再配布可能な構造Dataを使う`runtime_data`と、CorpusやWeb用例を存在・用法確認だけに使う`verification_only`に分ける。`PRIVATE`、`UNKNOWN`、`UNLICENSED`を含むLicenseは公開Runtime候補へ入れない。`verification_only`の本文はRuntime Assetへコピーせず、Source情報と審査結果だけを保持する。

対応`feature_type`:

- `onomatopoeia`
- `sensory_expression`
- `metaphor`
- `metonymy`
- `sociolect`
- `slang`
- `modality`
- `honorific`
- `treatment_expression`
- `discourse_marker`
- `backchannel`
- `sentence_final_particle`
- `information_territory`
- `interaction_rule`

## 全処理経路

```text
Web / Open Dictionary / Corpus Evidence / Masked unresolved log
    ↓
収集Data（YAMLまたはJSONL）
    ↓
tools/language_supply.py
    ├─ Source URL / SHA-256
    ├─ License
    ├─ runtime_data / verification_only
    └─ Private・不明Source拒否
    ↓
kind=language_feature のReview Bundle
    ↓
tools/reviewer.py
    ├─ Source / License / Digest再検証
    ├─ Meaning分離
    ├─ Context条件
    ├─ Positive / Negative / Boundary
    └─ action/socialはExternal Action Review必須
    ↓
tools/promote_language_features.py --apply
    ↓
dictionaries/system/language_features.d/*.yaml
    ↓
tools/compile_language_features.py
    ├─ Fragment承認StatusとSource SHA-256
    ├─ Schema検証
    ├─ Entry / Interpretation ID衝突検査
    ├─ Surface / Match Mode検証
    ├─ Evidence必須検査
    └─ Aho-Corasick遷移・Failure Linkを事前Compile
    ↓
dictionaries/system/compiled/language_features.d/
    ├─ manifest.json
    └─ part-*.b64
    ↓
Wheelへ同梱
    ↓
RuntimeはSHA-256検証済みの分割Assetを復号し、完成済みAutomatonを直接ロード
```

## Runtime反映

検出結果は`meaning_graph.language_features`へ出力するだけではなく、該当Clauseの命題へ次を反映する。

- 感覚表現 → `sensory_features`
- 若者言葉・スラング → `register_labels`、`sense_id`、`sense_label`
- 命令・依頼 → `force_level`、`directness`、`politeness_level`、`speech_act`
- 敬語 → `honorific_classes`、`social_relation_status`
- 相槌・終助詞 → `interaction_functions`、`information_territory`、`pragmatic_markers`

複数語義をContextで一つに絞れない場合は、候補IDを失わず`AMBIGUOUS`を返す。`risk_class=action`または`social`の曖昧性が残ったExternal Action要求はFail Closedとする。

Surface一致は用途別に分ける。

- `exact`: 句読点を除く発話全体一致
- `token`: 元文Spanと一致する単一Token
- `sentence_final`: 文末位置を要求
- 終助詞: 同一Spanを覆う連続Token列として確認し、動詞語尾の部分文字列を除外
- 重複終助詞: `よね`を`よ`と`ね`へ重複分解せず最長一致を保持

## Social Context

`AnalyzeRequest.social_context`は次を表現できる。

- speaker
- addressee
- mentioned_people
- 所属Group
- speakerとaddresseeのGroup差
- 役割・上下関係
- 場面
- Formality

これにより「申す」等を表面形だけで一つの敬語分類へ固定しない。Social Contextが不足し、複数の待遇解釈が残る場合は`AMBIGUOUS`とし、外部Actionへ通さない。

## 事前Compile契約

`LiteralIndex.to_compiled()`が遷移表、Failure Link、Output、Prefix Gateを固定化する。Compilerは完成PayloadをBase64分割し、各Partと全PayloadのSHA-256をManifestへ記録する。Runtimeは各Digestを検証して復号した後、`LiteralIndex.from_compiled()`で復元し、Failure Linkを構築し直さない。

Source Fragmentは`approvals.yaml`へ承認Status、Source SHA-256、Review IDを固定する。承認後に1文字でも変更されたFragmentはCompileを拒否する。

SourceまたはCompiler変更時は`Compile Language Assets` workflowが完成Assetを再生成し、同一Branchへ記録する。Wheel Buildは`--check`を通過しない限り失敗する。

## 検証契約

CIで次を強制する。

- 収集DataがReview専用Proposalになり直接昇格しない
- 外部EvidenceにSource URL、SHA-256、License、Scopeがある
- Private・License不明・未追跡Evidenceを拒否する
- Positive / Negative / Boundaryとaction/social Reviewがそろう
- 未承認FragmentをCompileできない
- Source YAMLとCompiled AssetがByte単位で同期している
- Compiled Assetを二回生成して同一Byte列になる
- 各Partと全PayloadのDigestが一致する
- Compiled Automatonを再構築なしでロードできる
- `エグい`の肯定・否定・曖昧性と候補保持
- オノマトペの感覚Parameter
- 命令強度Lv5
- `絶対に成功する`を命令と誤認しない
- 敬語のSocial Context
- Social Context不足時のFail Closed
- `はい。`を相槌として認識する
- `死ね。`の語尾を終助詞「ね」と誤認しない
- `よね`と`よ`・`ね`の重複抑止
- 既存Gold、External Action Guard、Offline Wheel、10ms/50ms契約を維持する

## 完了条件

- 収集Dataが`language_feature` Proposalへ変換できる
- Reviewerが高度言語Featureを審査できる
- PromotionがTransactionalである
- Source YAMLからCompiled Assetを再現できる
- WheelにSourceとCompiled Assetが含まれる
- RuntimeがMeaning Graphへ反映する
- 曖昧なAction / Social解釈を外部実行へ通さない
- 既存Intent / Task / External Action Guardを削除しない
