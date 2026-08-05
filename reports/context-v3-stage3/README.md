# Context v3 第3段階の現在結果

<p align="center">
  <strong>日本語</strong> ｜ <a href="README_EN.md">English</a>
</p>

## 結論

5,000件すべてを、第3段階の確認待ちQueueへ欠落なく整理しました。

さらに最初のReview対象である「部分文字列による誤抽出疑い」39件を全件確認し、38件をepistemic候補から除外、`いいかも`1件を直接使用例・意味・ScopeのEvidence確認へ戻しました。

これは採用完了ではありません。承認済み0件、Runtime昇格0件を維持しています。

## 初期分類結果

| 区分 | 件数 | 現在の扱い |
|---|---:|---|
| Source・License確認待ち | **1,913** | 根拠がそろうまで停止 |
| 外部操作Risk確認 | **250** | 命令・変更・参照対象を重点確認 |
| 人によるEvidence確認へ進める | **1,508** | 使用実態・意味・文脈を確認 |
| Category不一致の疑い | **1,290** | 人名・地名・通常語・誤分類を確認 |
| 部分文字列による誤抽出の疑い | **39** | 明示Decision Ledgerで全件確認 |
| 合計 | **5,000** | 自動承認・自動却下なし |

## 手動Decision反映後

| 区分 | 件数 |
|---|---:|
| Source・License確認待ち | **1,913** |
| 外部操作Risk確認 | **250** |
| 人によるEvidence確認へ進める | **1,509** |
| Category不一致の疑い | **1,290** |
| Review済み除外 | **38** |
| 部分文字列誤抽出の未確認残 | **0** |
| Runtime昇格 | **0** |

### 第1Review Batchの判断

- `かものはし`、`かもしか`、`さかもと`、`何もかも`、`しかも`など38件は、語彙内部に含まれる文字列を推量標識`かも`として誤認した候補のため除外。
- `いいかも`は「いい」＋推量の`かも`として機能し得るため、誤抽出として除外せずEvidence確認へ戻した。
- どの候補もMeaning Graph、Intent、Task、External Action、Runtimeへ昇格していない。
- 自動却下ではなく、チェックイン済みの明示Decision LedgerだけをToolが適用する。

Decision Ledger：

- `research/context_collection/stage3_decisions/epistemic-substring-decisions-v1.jsonl`
- `reports/context-v3-stage3/decision-summary.json`
- `reports/context-v3-stage3/runtime-boundary-after-decisions.json`

## 発見した主な問題

- 5,000件すべてに、実際の使用例を直接確認する作業が残っている。
- 1,913件はLicenseが`確認中`で、そのまま採用できない。
- 1,695件は、割り当てられたCategoryを支持する根拠が不足している。
- 500件はCategoryとFeature Typeが一致していない。
- 210件は人名・地名として扱うべき可能性がある。
- 初期分類で39件あった部分文字列誤抽出疑いは、第1Review Batchで未確認残0件まで処理した。
- 800件は外部操作への影響確認が必要である。

具体例：

- `和田`がDialect候補へ入っていた。
- `かものはし`、`さかもと`、`何もかも`などがEpistemic候補へ入っていた。
- `削除しろ`などの命令候補は、License確認とExternal Action Reviewの両方が必要である。

## Review Pack

5,000件を最大20件ずつ、**260 Pack**へ分割しました。

各GitHub Actions実行では次をArtifactとして生成します。

- `review-queue.jsonl`：5,000件の初期判定
- `review-packs.jsonl`：260 Packの完全情報
- `review-pack-index.json`：第三者検証へ使う軽量Index
- `summary.json`：初期集計
- `runtime-boundary.json`：初期の自動昇格禁止境界
- `applied-decisions.jsonl`：明示Decisionの適用結果
- `post-decision-queue.jsonl`：Decision反映後の5,000件Queue
- `decision-summary.json`：Decision反映後集計
- `runtime-boundary-after-decisions.json`：Decision反映後もRuntime昇格0を示す境界

## 固定Digest

| 対象 | SHA-256 |
|---|---|
| 元Manifest | `c212ecfe662cb76bc5a40061b351af49b75876c4d4aad5036f3e0b41c5c8b04c` |
| 全Review Queue | `917de3ef2b391f07dd300f66a9ac1d98ad22f9a0ed9b0a33753e9690f321fce6` |
| 全Review Pack | `57c26478b26aef31f39ce1a086b69e481cc955a4cbe711b863c6620b82a973da` |
| Substring Decision Ledger | `bc907632f87da3443a4d928972e740a849e8096fb5cd3b2ca5d342e00c982c8e` |
| Decision反映後Queue | `233c6dd096f325e2e5ee1c3830fc266bfaffc8fd2826c0dd5b53efff476ed764` |

## 次に行うこと

第3段階の続きは、次の順序で進めます。

```text
明確な部分文字列誤抽出：39件Review完了
  ↓
Category不一致疑い：1,290件
  ↓
外部操作Risk候補：250件
  ↓
Source・License確認待ち：1,913件
  ↓
人による意味・文脈Evidence確認
  ↓
肯定・否定・境界・引用・疑問・仮定・伝聞Test
  ↓
Gold Case・独立Holdout
  ↓
承認候補だけ第4段階へ
```

候補数を維持するために誤った候補を残すことはしません。却下後に件数が減っても、それを正しい第3段階結果として扱います。
