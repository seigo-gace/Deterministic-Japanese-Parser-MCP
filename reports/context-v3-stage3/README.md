# Context v3 第3段階の現在結果

<p align="center">
  <strong>日本語</strong> ｜ <a href="README_EN.md">English</a>
</p>

## 結論

5,000件すべてを、第3段階の確認待ちQueueへ欠落なく整理しました。

- 第1Review Batch：部分文字列誤抽出疑い39件を全件確認し、38件を除外、`いいかも`1件をEvidence Reviewへ戻した。
- Category Batch 001：人名・地名疑い20件を確認し、modality誤分類10件を除外、honorific候補10件をEvidence Reviewへ戻した。
- Category Batch 002：次の20件を確認し、地名・行政区・駅名・元号18件を除外、`世尊`と地域語`鮎掛`をEvidence Reviewへ戻した。

承認済み0件、Runtime昇格0件、自動Category付替え0件を維持しています。

## 初期分類結果

| 区分 | 件数 | 現在の扱い |
|---|---:|---|
| Source・License確認待ち | **1,913** | 根拠がそろうまで停止 |
| 外部操作Risk確認 | **250** | 命令・変更・参照対象を重点確認 |
| 人によるEvidence確認へ進める | **1,508** | 使用実態・意味・文脈を確認 |
| Category不一致の疑い | **1,290** | 人名・地名・通常語・誤分類を確認 |
| 部分文字列による誤抽出の疑い | **39** | 明示Decision Ledgerで全件確認 |
| 合計 | **5,000** | 自動承認・自動却下なし |

## 現在のDecision反映後

| 区分 | 件数 |
|---|---:|
| Source・License確認待ち | **1,913** |
| 外部操作Risk確認 | **250** |
| 人によるEvidence確認へ進める | **1,521** |
| Category不一致の疑い | **1,250** |
| Review済み除外 | **66** |
| 部分文字列誤抽出の未確認残 | **0** |
| Runtime昇格 | **0** |

### 第1Review Batch｜部分文字列誤抽出

- `かものはし`、`かもしか`、`さかもと`、`何もかも`、`しかも`など38件をepistemic候補から除外。
- `いいかも`は実際の推量用法を持ち得るためEvidence Reviewへ戻した。

### Category Batch 001｜人名・地名疑い

- **除外10件**：`GHQ/SCAP`、`コモロ`、`京女`、`マスティク島`、`GHQ`、`こどもの日`、`メイ`、`メイヨー`、`ダマスカス`、`ラーマーヤナ`
- **Evidence Review継続10件**：`入道前太政大臣`、`後京極摂政前太政大臣`、`揚子`、`お釈迦さま`、`よびすて`、`仲尼`、`法性寺入道前関白太政大臣`、`儀同三司母`、`後徳大寺左大臣`、`かわらのさだいじん`

### Category Batch 002｜人名・地名疑い

- **除外18件**：`奥田`、`上越`、`宮崎県`、`鹿児島県`、`茨木`、`入來`、`永野`、`山陰`、`薩摩川内`、`出水`、`秋津`、`佐賀`、`徳島県`、`名古屋`、`福岡県`、`昭和`、`筑紫`、`高市`
- **Evidence Review継続2件**：`世尊`、`鮎掛`
- `世尊`は釈迦を指す敬称名として元Glossがhonorific機能を直接示す。
- `鮎掛`はsource tagsに`regional`、`kagoshima`、`regional Japanese`があり、地域語としてdialectとの関係が成立し得る。
- 除外18件は市・県・旧町・地域・駅・元号等のEntityであり、表層単独をdialect表現として扱う根拠がない。

## Decision Evidence

- `research/context_collection/stage3_decisions/epistemic-substring-decisions-v1.jsonl`
- `research/context_collection/stage3_decisions/category-name-place-batch-001.jsonl`
- `research/context_collection/stage3_decisions/category-name-place-batch-002.jsonl`
- `tools/apply_context_v3_stage3_decisions.py`
- `tools/apply_context_v3_stage3_category_decisions.py`
- `reports/context-v3-stage3/decision-summary.json`
- `reports/context-v3-stage3/category-batch-001-summary.json`
- `reports/context-v3-stage3/category-batch-002-summary.json`
- `reports/context-v3-stage3/runtime-boundary-after-category-batch-002.json`

## 集計補正

- `name-or-place-candidate`フラグ総数は**210件**。
- そのうち初期のCategory不一致Queueにいたのは**206件**。
- 残る4件はSource・License等の別停止区分にいる。
- Category Batch 001・002で40件を処理したため、同Queueの人名・地名フラグ未確認残は**166件**。

## 発見した主な問題

- 5,000件すべてに、実際の使用例を直接確認する作業が残っている。
- 1,913件はLicenseが`確認中`で、そのまま採用できない。
- 1,695件は、割り当てられたCategoryを支持する根拠が不足している。
- 500件はCategoryとFeature Typeが一致していない。
- 800件は外部操作への影響確認が必要である。

## Review PackとArtifact

5,000件を最大20件ずつ、**260 Pack**へ分割しています。GitHub Actionsでは初期Queue、部分文字列Decision、Category Batch 001、Category Batch 002を順序適用し、各集計・Runtime境界を毎回再生成してチェックイン済みEvidenceとの差分を検証します。

Category ApplicatorはBatch IDから出力名を決定するため、BatchごとにToolを複製せず、明示Decision Ledgerを追加して順序適用します。

## 固定Digest

| 対象 | SHA-256 |
|---|---|
| 元Manifest | `c212ecfe662cb76bc5a40061b351af49b75876c4d4aad5036f3e0b41c5c8b04c` |
| 全Review Queue | `917de3ef2b391f07dd300f66a9ac1d98ad22f9a0ed9b0a33753e9690f321fce6` |
| 全Review Pack | `57c26478b26aef31f39ce1a086b69e481cc955a4cbe711b863c6620b82a973da` |
| Substring Decision Ledger | `bc907632f87da3443a4d928972e740a849e8096fb5cd3b2ca5d342e00c982c8e` |
| Category Batch 001 Decision Ledger | `117a32a6fa7d09d49d72e33194fe551fdf58f09dbf6d97f66ed3109d8a0a9386` |
| Category Batch 002 Decision Ledger | `9b91327b4ff3a882b5ae5d1ec97a9f91cfb10277fbafc10b88ef76b41a23f671` |

## 次に行うこと

```text
部分文字列誤抽出：39件Review完了
  ↓
Category人名・地名疑い Batch 001：20件Review完了
  ↓
Category人名・地名疑い Batch 002：20件Review完了
  ↓
Category不一致疑い残：1,250件
  ↓
外部操作Risk候補：250件
  ↓
Source・License確認待ち：1,913件
  ↓
意味・文脈Evidence／Scope Test／Gold Case／独立Holdout
  ↓
承認候補だけ第4段階へ
```

候補数を維持するために誤った候補を残したり、別Categoryへ自動移動したりしません。却下後に件数が減ることを、正しい第3段階結果として扱います。
