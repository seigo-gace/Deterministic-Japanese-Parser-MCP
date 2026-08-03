# Dictionary Expansion Review — 2026-08

## 1. 目的

Deterministic Japanese Parser MCPの辞書を、既存の開発・設計中心の語彙から、日常指示、業務会話、文書作成、障害対応、意思決定、担当・期限・合意形成まで拡張する。

単にEntry数を増やすのではなく、実際に使われる可能性、意味の安定性、Intent／Taskへの変換可能性、既存Entryとの衝突、字義用法との競合を確認したうえで追加する。

## 2. 調査基盤

- 国立国語研究所『現代日本語書き言葉均衡コーパス』語彙表（BCCWJ）
  - https://clrd.ninjal.ac.jp/bccwj/freq-list.html
- NINJAL-LWP for BCCWJ
  - https://nlb.ninjal.ac.jp/
- 国立国語研究所『日本語日常会話コーパス』（CEJC）語彙表・談話行為情報
  - https://www2.ninjal.ac.jp/conversation/cejc.html
  - https://www2.ninjal.ac.jp/conversation/cejc-monitor/cejc-wc.html
- 国立国語研究所コーパスポータル／日本語Webコーパス
  - https://clrd.ninjal.ac.jp/
- GitHub公式Documentのmerge／revert／rebase等の用法
  - https://docs.github.com/ja/
- デジタル庁デザインシステム
  - https://design.digital.go.jp/
- Microsoft Learnの技術文書・用語一貫性Guideline
  - https://learn.microsoft.com/ja-jp/contribute/content/style-quick-start

第三者辞書の定義文はコピーしない。上記資料は、使用領域・用例傾向・表記・語の組合せを確認するために利用し、`interpretation`はProject独自に記述する。

## 3. 採用基準

1. 現代日本語の書き言葉、日常会話、業務、開発のいずれかで実用性が高い。
2. 表現から、Action、Constraint、状態、談話機能のいずれかへ変換できる。
3. 既存Entryとの差分を説明できる。
4. 短く多義的な表現は`context_policy: required_any`で誤検出を抑えられる。
5. Gold Corpusへ自然な例文を追加できる。
6. 特定企業だけの内輪語、意味が急変しやすい流行語、侮蔑的表現へ過度に依存しない。

## 4. 第1回採用：比喩・慣用表現48件

### 4.1 日常指示・作業進行

| 表現 | 意味・意図 | 採用理由 | Risk制御 |
|---|---|---|---|
| 一旦置く | 議論・判断・作業を一時保留する | 会話・業務で頻出する保留表現 | 議論／判断／作業Context必須 |
| 巻き取る | 他者の担当・対応を引き受ける | Task移管の実務表現 | 担当／Task／対応Context必須 |
| 持ち越す | 未解決事項を後続回へ送る | 会議・Projectで頻出 | 課題／会議／期限Context必須 |
| 先に進める | 非Blocking事項を待たず次工程へ進む | 明示的な進行判断に使える | 工程／作業Context必須 |
| 要点を押さえる | 重要事項を確認・保持する | 読解・説明・確認で有用 | 固定句として採用 |
| ざっくり出す | 粗い初期案・概算を作る | 初期検討で頻出 | 案／概算／見積Context必須 |
| きっちり詰める | 詳細を具体化し未確定をなくす | 「詰める」より精度要求が明確 | 設計／条件／仕様Context必須 |
| バラして考える | 問題を要素分解する | Task分解・分析に直結 | 問題／要件／構造Context必須 |
| まとめて片付ける | 関連項目を一括完了する | 一括処理Intentに使える | Task／課題Context必須 |
| 手短にまとめる | 要点だけを短く整理する | 文書・回答指示で実用性が高い | 固定句として採用 |
| 確認を取る | 関係者から明示確認を得る | 承認・合意の前段を識別できる | 担当／相手／承認Context必須 |
| 話を切る | 現在の議論を終了する | 会話制御に必要 | 会議／議論Context必須 |

### 4.2 業務Communication・組織

| 表現 | 意味・意図 | 採用理由 | Risk制御 |
|---|---|---|---|
| すり合わせる | 前提・認識・詳細を一致させる | 要件定義・合意形成で頻出 | 認識／要件／条件Context必須 |
| 話を通す | 関係者へ説明し了解または承認を得る | 組織内承認を表す | 承認／上長／関係者Context必須 |
| 根回しする | 正式決定前に関係者へ説明・調整する | 意思決定前工程として有用 | 組織／承認Context必須 |
| 持ち帰る | その場で決定せず内部確認へ戻す | 会議の保留Speech Act | 会議／確認Context必須 |
| 宿題にする | 未解決事項を後続Taskとして割り当てる | Task化へ直接変換可能 | 課題／会議Context必須 |
| 腹を割る | 建前を外して率直に話す | 発話Style・交渉状態を示す | 会話／交渉Context必須 |
| 落とし所を探る | 合意可能な妥協点を探索する | 比較・交渉に有用 | 交渉／合意Context必須 |
| 風向きを見る | 関係者・市場・状況の方向を見極める | 判断前の観察を示す | 市場／組織／状況Context必須 |
| 板挟みになる | 相反する要求の間で動けない | Conflict状態の認識に有用 | 要求／関係者Context必須 |
| 声を拾う | 利用者・現場の意見を収集する | 要求収集と結び付く | 利用者／現場Context必須 |
| 汲み取る | 明示されていない意図を文脈から理解する | 読解目的に重要 | 意図／要望／文脈Context必須 |
| 口火を切る | 議論・作業を最初に開始する | 開始・順序認識に有用 | 議論／会議／作業Context必須 |

### 4.3 開発・運用・障害対応

| 表現 | 意味・意図 | 採用理由 | Risk制御 |
|---|---|---|---|
| 切り分ける | 原因または責任範囲を分離して特定する | 障害対応の中心語 | 障害／原因／環境Context必須 |
| 再現を取る | 同じ条件で問題を再発させ確認する | Debugの主要工程 | バグ／障害／手順Context必須 |
| ログを追う | Logの時系列から処理・原因を確認する | 調査Actionへ変換可能 | ログ／障害Context必須 |
| 影響範囲を洗う | 変更・障害が及ぶ対象を網羅確認する | Risk判定に必須 | 変更／障害Context必須 |
| 暫定対応を入れる | 被害抑制の一時対策を適用する | 恒久対応と区別可能 | 障害／緊急Context必須 |
| 恒久対応を入れる | 原因を除去する長期的修正を適用する | 再発防止Workflowに必要 | 原因／再発Context必須 |
| 巻き戻す | 変更前の状態へ戻す | Rollbackの一般的な日本語 | 変更／VersionContext必須 |
| 凍結する | 変更・公開・受付を一時停止する | Change freezeを表す | 変更／ReleaseContext必須 |
| 塩漬けにする | 問題・資産を長期間未処理で残す | 技術的負債の状態表現 | 課題／負債Context必須 |
| デグレする | 変更により既存機能が悪化する | 開発現場で一般的 | 変更／機能／TestContext必須 |
| 依存を剥がす | Component間依存を除去・弱化する | Architecture変更に有用 | Module／LibraryContext必須 |
| 責務を切る | 機能・Moduleの担当範囲を分離する | 設計・分割Intentに直結 | Module／設計Context必須 |

### 4.4 文書・読解・説明

| 表現 | 意味・意図 | 採用理由 | Risk制御 |
|---|---|---|---|
| 骨子を作る | 文書・提案の中心構造を作る | 文書Workflowに必要 | 文書／提案Context必須 |
| 肉付けする | 骨子へ根拠・詳細・例を加える | Draft拡張を識別できる | 文書／説明Context必須 |
| 軸を通す | 主張・判断基準を一貫させる | Coherence検査に有用 | 主張／構成Context必須 |
| 筋を通す | 論理または手続を一貫させる | 論理・手続の二候補を保持可能 | 論理／手続Context必須 |
| 噛み砕く | 難しい内容を理解しやすく言い換える | 説明変換Intentに直結 | 説明／用語Context必須 |
| 具体に落とす | 抽象概念を実行可能な内容へ変換する | Task化へ直結 | 設計／計画Context必須 |
| 抽象度を上げる | 個別事象を上位概念へ一般化する | 分析・要約に有用 | 分析／概念Context必須 |
| 抽象度を下げる | 上位概念を具体例・手順へ展開する | 実装化・説明に有用 | 設計／手順Context必須 |
| 話が飛ぶ | 論理的接続なしに別論点へ移る | Coherence問題を検出できる | 議論／文章Context必須 |
| ねじれを直す | 主述・修飾・視点の不整合を修正する | 日本語記述検査に重要 | 文／主語／述語Context必須 |
| 見出しを立てる | 内容を区分するHeadingを設ける | 文書構造Actionとして明確 | 文書／PageContext必須 |
| 一文一義にする | 一文へ一つの主要命題だけを置く | 読みやすさ検査に有用 | 文書／文章Context必須 |

## 5. 第1回採用：Intent Rule 63件

21 Intent Typeすべてへ3 Patternずつ追加する。

- action：`しておいて`、`進めてくれ`、`済ませろ`
- comparison：`違いを出す`、`どちらが適切`、`差分を明確にする`
- completion_criteria：`完了条件は`、`できたら完了`、`をもって完了`
- condition：`の場合は`、`もし〜なら`、`〜次第`
- correction：`違う、`、`正確には`、`ではなく`
- decision：`で決定`、`これでいく`、`正式採用`
- dependency：`終わってから`、`に依存する`、`なしでは進められない`
- exception：`以外は`、`ただし`、`だけは`
- modify：`直して`、`更新して`、`変更してくれ`
- out_of_scope：`対象外`、`触らない`、`含めない`
- premise：`前提として`、`を前提に`、`そもそも`
- preserve：`そのまま`、`変えずに`、`消さない`
- priority：`最優先で`、`を先に`、`優先順位は`
- prohibition：`はやめろ`、`触るな`、`しないこと`
- question：`って何`、`なぜ`、`どうすればいい`
- reference：`さっきの`、`前の案`、`この部分／その内容／上記`
- remove：`消して`、`なくして`、`廃止して`
- request：`してくれ`、`を頼む`、`対応してくれ`
- scope：`対象は`、`だけに限定`、`に絞って`
- sequence：`まず〜次に`、`してから`、`最後に`
- verification_criteria：`合格条件は`、`が通ること`、`をもって合格`

全Patternは固定Literalを含め、RuntimeのRule Indexに載る構造とする。

## 6. 第1回採用：Synonym／Canonical Group

既存20 GroupのSurfaceを増やし、次の20 Groupを新設する。

`依頼 / 承認 / 合意 / 担当 / 移管 / 保留解除 / 再現 / 原因特定 / 影響確認 / 暫定対応 / 恒久対応 / 凍結 / 解除 / 要約 / 具体化 / 抽象化 / 説明 / 整合 / 分割 / 一括処理`

同じSurfaceが複数Groupに属する場合は、Canonicalizerが候補集合を保持する。意味を一つへ潰さない。

## 7. 第1回採用：Workflow 10件

1. requirement_analysis
2. bug_reproduction
3. root_cause_analysis
4. document_revision
5. data_migration
6. dependency_upgrade
7. account_auth_change
8. ui_accessibility_review
9. knowledge_base_update
10. rollback_recovery

各Workflowは、準備・実行・検証・記録を省略しない。

## 8. 保留・除外

| 候補 | 判定 | 理由 |
|---|---|---|
| やばい | 除外 | 肯定・否定・驚き・危険の意味が広過ぎる |
| えぐい | 除外 | 世代・Contextにより評価極性が変わる |
| 神 | 除外 | 対象・評価・固有名詞の衝突が大きい |
| 落とす | 保留 | 削除、変換、Deploy、価格低下、説明具体化など多義性が極端に高い |
| 回す | 保留 | 実行、転送、担当移管、回転、循環など候補が多い |
| 上げる／下げる | 除外 | 単独では対象・尺度・方向を確定できない |
| いい感じに | 除外 | 完了条件を持たず、外部Actionへ使用できない |
| 適当に | 保留 | 「適切に」と「雑に」の両義性がある |
| 飛ぶ | 除外 | 移動、消失、Skip、論理飛躍、Network断の衝突が大きい |
| 丸める | 保留 | 数値丸め、文章要約、対立収束、Object整形が競合する |
| 握る | 既存維持・拡張なし | 単独語は多義的。既存Entry以上にAliasを増やさない |
| 拾う | 既存維持・拡張なし | 字義用法と要求収集用法が競合する |

## 9. 検証条件

- Manifest count一致
- Metaphor Surface／Alias衝突0
- Rule ID重複0
- 全Regex Compile成功
- 新規Entryを含むGold Corpus 60件以上追加
- Indexed／Exhaustive Semantic Parity
- Python 3.10／3.12 pytest
- Existing Gold回帰なし
- 追加後のDictionary Scale Test
- Astera call-through p95 10ms以下、最大50ms以下
- Offline Wheel Install成功

## 10. 完了判定

候補一覧作成だけでは完了としない。辞書File、Manifest、Gold、Test、README、Notion正本、GitHub Commit、CI Evidenceまで揃った時点を完了とする。
