# Context v3 第3段階レビュー

<p align="center">
  <strong>日本語</strong> ｜ <a href="CONTEXT_V3_STAGE3_REVIEW_EN.md">English</a>
</p>

## 結論

Context v3の5,000件は、第1段階の収集・正規化と第2段階の候補生成まで完了しています。

第3段階では、候補をそのまま採用せず、次を確認します。

- 実際の使用例と出典
- 意味と使用文脈
- 分類の正しさ
- 部分文字列による誤抽出
- 人名・地名・通常語の誤分類
- 読みと表記揺れ
- ライセンスと再配布条件
- 肯定例・否定例・境界例
- 引用・否定・疑問・仮定・伝聞
- 外部操作へ影響する危険性
- 独立した人による確認

第3段階が完了するまで、候補をMeaning Graphの確定意味、意図、Task、外部操作へ自動昇格しません。

## #11と#15を洗い直した結果

PR #11は、12万件の語彙を実行用索引へ変換し、ParserとMeaning Graphへ語彙候補として接続しました。

PR #15は、Context v3の5,000件候補を追加しました。しかし、PR #15の変更範囲には、候補生成物だけでなくPR #11由来の実行用辞書、索引、Workflow、検証Reportも混在していました。

さらに当時のWorkflowには、生成後にBranchへCommit・Pushする処理がありました。このため、次の境界が不明確になっていました。

```text
12万件の実行基盤
候補生成
第3段階のEvidence Review
Runtimeへの昇格
```

PR #20で12万件の実行基盤とWorkflowのBranch書込問題を修正しました。第3段階は、その修正済みmainを基準に独立して再開します。

## 第3段階の入力正本

第3段階では、次を入力正本とします。

```text
research/context_collection/expansion_v3/
├── manifest.json
└── 10Category配下の5,000 YAML
```

空だった`all_entries.jsonl`と`all_entries.csv`は正本として扱わず削除します。

Manifestが保証する現在の境界：

- 候補数：5,000
- 正規化後の重複：0
- 全件：`needs-evidence`
- 意味完成の主張：禁止
- Runtime昇格：禁止

## 自動で行う範囲

`tools/review_context_v3_stage3.py`は、5,000件を一件も欠かさず読み取り、次を機械的に整理します。

- Source・License不足
- 分類とFeature Typeの不一致
- 部分文字列による誤抽出候補
- 人名・地名候補
- Source MetadataのNoise
- 外部操作Reviewが必要な表現
- 直接使用Evidenceが必要な候補
- 人によるEvidence Reviewへ進める候補

出力：

```text
summary.json
review-queue.jsonl
review-packs.jsonl
runtime-boundary.json
```

Review Packは20件以下に分割します。

## 自動で行わない範囲

この処理は、次を自動で行いません。

- 候補の承認
- 候補の最終却下
- 意味の創作
- 外部辞書本文の転載
- 452件の比喩・語用表現への追加
- 339件の判定規則への追加
- 100個の類義語Groupへの追加
- Task・Workflowへの追加
- Runtime辞書への昇格
- 外部操作の許可

自動分類は、人が確認する順番を整理するためのものです。

## 第3段階の判定区分

| 区分 | 意味 |
|---|---|
| `blocked-source-or-license` | 出典またはLicenseが未確認 |
| `suspected-substring-artifact` | 文字列の一部だけを根拠に誤分類された疑い |
| `suspected-category-mismatch` | 人名・地名・通常語など、Categoryが不適切な疑い |
| `high-risk-action-review` | 命令・削除・変更など外部操作への影響を確認する必要あり |
| `ready-for-human-evidence-review` | 構造上は人のEvidence Reviewへ進められる |

どの区分でも、自動昇格はしません。

## 完了条件

第3段階の完了は「5,000件を機械的に分類した」時点ではありません。

候補ごとに必要な確認を終え、承認・却下・保留を人が決定し、承認候補について次をそろえた時点です。

- 公開Sourceと固定Version
- Source Digest
- 適用License
- 意味とContext
- 読みとVariant
- 肯定・否定・境界例
- 引用・否定・疑問・仮定・伝聞Test
- 衝突確認
- External Action Review
- Gold Case
- 独立Holdout
- 人による最終承認

第4段階は、この条件を通過した候補だけを実行用AssetへCompileします。
