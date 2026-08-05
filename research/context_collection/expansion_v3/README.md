# Context Data Expansion v3 — 5,000 Candidates

## 現在の段階

| 段階 | 状態 |
|---|---|
| 第1段階：収集・正規化 | 完了 |
| 第2段階：Context候補生成 | 完了 |
| 第3段階：Evidence・分類・衝突・安全性Review | 進行中 |
| 第4段階：承認済みDataのRuntime Compile | 未開始 |

候補数は**5,000件**です。全件が`needs-evidence`であり、Runtimeへの自動昇格は禁止されています。

## Category件数

- `slang`: 1,000
- `onomatopoeia`: 700
- `modality`: 500
- `honorific`: 500
- `discourse`: 400
- `metaphor`: 500
- `dialect`: 400
- `media_community`: 500
- `reference`: 300
- `epistemic`: 200

## 第3段階の入力正本

```text
manifest.json
10Category配下の5,000 YAML
```

空だった`all_entries.jsonl`と`all_entries.csv`は削除し、正本として扱いません。

## 第3段階の処理

```bash
python tools/review_context_v3_stage3.py \
  --input-root research/context_collection/expansion_v3 \
  --output-root reports/context-v3-stage3 \
  --pack-size 20
```

この処理は全5,000件を次のReview Queueへ分けます。

- Source・License不足
- 部分文字列による誤抽出疑い
- Category不一致疑い
- 外部操作Risk Review
- 人によるEvidence Reviewへ進める候補

自動承認・自動却下・Runtime昇格は行いません。

詳細：

- [`../../../docs/CONTEXT_V3_STAGE3_REVIEW.md`](../../../docs/CONTEXT_V3_STAGE3_REVIEW.md)
- [`../../../docs/CONTEXT_V3_STAGE3_REVIEW_EN.md`](../../../docs/CONTEXT_V3_STAGE3_REVIEW_EN.md)

## 重要な境界

5,000件は候補発見数です。次を証明する数字ではありません。

- 意味の正確性
- 現在の使用実態
- Categoryの正しさ
- Licenseの確認完了
- Runtimeでの安全性
- 5,000件すべての採用

第3段階と人によるReviewを通過した候補だけが、第4段階へ進めます。
