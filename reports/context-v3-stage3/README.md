# Context v3 第3段階の現在結果

<p align="center">
  <strong>日本語</strong> ｜ <a href="README_EN.md">English</a>
</p>

## 結論

5,000件すべてを、第3段階の確認待ちQueueへ欠落なく整理しました。

これは採用完了ではありません。現在も承認済み0件、Runtime昇格0件です。

## 全体結果

| 区分 | 件数 | 現在の扱い |
|---|---:|---|
| Source・License確認待ち | **1,913** | 根拠がそろうまで停止 |
| 外部操作Risk確認 | **250** | 命令・変更・参照対象を重点確認 |
| 人によるEvidence確認へ進める | **1,508** | 使用実態・意味・文脈を確認 |
| Category不一致の疑い | **1,290** | 人名・地名・通常語・誤分類を確認 |
| 部分文字列による誤抽出の疑い | **39** | 原則として除外候補、最終判断待ち |
| 合計 | **5,000** | 自動承認・自動却下なし |

## 発見した主な問題

- 5,000件すべてに、実際の使用例を直接確認する作業が残っている。
- 1,913件はLicenseが`確認中`で、そのまま採用できない。
- 1,695件は、割り当てられたCategoryを支持する根拠が不足している。
- 500件はCategoryとFeature Typeが一致していない。
- 210件は人名・地名として扱うべき可能性がある。
- 39件は、`かも`を含むだけの単語を推量表現として拾った疑いがある。
- 800件は外部操作への影響確認が必要である。

具体例：

- `和田`がDialect候補へ入っていた。
- `かものはし`、`さかもと`、`何もかも`などがEpistemic候補へ入っていた。
- `削除しろ`などの命令候補は、License確認とExternal Action Reviewの両方が必要である。

## Review Pack

5,000件を最大20件ずつ、**260 Pack**へ分割しました。

各GitHub Actions実行では次をArtifactとして生成します。

- `review-queue.jsonl`：5,000件の全判定
- `review-packs.jsonl`：260 Packの完全情報
- `review-pack-index.json`：第三者検証へ使う軽量Index
- `summary.json`：集計
- `runtime-boundary.json`：自動昇格禁止の境界

## 固定Digest

| 対象 | SHA-256 |
|---|---|
| 元Manifest | `c212ecfe662cb76bc5a40061b351af49b75876c4d4aad5036f3e0b41c5c8b04c` |
| 全Review Queue | `917de3ef2b391f07dd300f66a9ac1d98ad22f9a0ed9b0a33753e9690f321fce6` |
| 全Review Pack | `57c26478b26aef31f39ce1a086b69e481cc955a4cbe711b863c6620b82a973da` |

## 次に行うこと

第3段階の続きは、次の順序で進めます。

```text
明確な部分文字列誤抽出とCategory不一致
  ↓
外部操作Risk候補
  ↓
Source・License確認待ち
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
