# Current Context v3 Stage 3 Result

<p align="center">
  <a href="README.md">Japanese</a> ｜ <strong>English</strong>
</p>

## Status

All 5,000 candidates are accounted for in the Stage 3 review queue.

- Substring batch: 39 reviewed, 38 rejected, and `いいかも` returned to evidence review.
- Category batch 001: 20 reviewed, 10 modality mismatches rejected, and 10 honorific-related entries retained for evidence review.
- Category batch 002: 20 reviewed, 18 place/entity mismatches rejected, and `世尊` plus the regional lexeme `鮎掛` retained for evidence review.

Approved entries, runtime promotions, and automatic reclassification remain at zero.

## Current status after explicit decisions

| Review status | Count |
|---|---:|
| Blocked on source or license | **1,913** |
| High-risk external-action review | **250** |
| Ready for human evidence review | **1,521** |
| Suspected category mismatch | **1,250** |
| Reviewed and rejected | **66** |
| Runtime promotions | **0** |

## Category batch 002

The original gloss, `source_pos`, and source tags were inspected for every entry.

- **Rejected:** `奥田`, `上越`, `宮崎県`, `鹿児島県`, `茨木`, `入來`, `永野`, `山陰`, `薩摩川内`, `出水`, `秋津`, `佐賀`, `徳島県`, `名古屋`, `福岡県`, `昭和`, `筑紫`, and `高市`.
- **Retained for evidence review:** `世尊` and `鮎掛`.
- `世尊` is explicitly defined as an honorific name for Gautama Buddha.
- `鮎掛` carries regional, Kagoshima, and regional-Japanese source tags, so it may be a genuine regional lexeme.
- The rejected entries are cities, prefectures, former towns, regions, stations, an era name, or surnames. A location name may modify a dialect label, but the standalone surface is not itself a dialect expression.
- No entry was automatically moved to another category or promoted into Meaning Graph, intent, task, external action, or runtime data.

## Count correction

- The total number of entries carrying the `name-or-place-candidate` flag is **210**.
- **206** of them were initially in the suspected-category-mismatch queue.
- The other four are blocked under different primary statuses such as source or license review.
- After category batches 001 and 002, **166** name-or-place flagged entries remain unreviewed in the category-mismatch queue.

## Decision evidence

- `research/context_collection/stage3_decisions/epistemic-substring-decisions-v1.jsonl`
- `research/context_collection/stage3_decisions/category-name-place-batch-001.jsonl`
- `research/context_collection/stage3_decisions/category-name-place-batch-002.jsonl`
- `tools/apply_context_v3_stage3_category_decisions.py`
- `reports/context-v3-stage3/category-batch-001-summary.json`
- `reports/context-v3-stage3/category-batch-002-summary.json`
- `reports/context-v3-stage3/runtime-boundary-after-category-batch-002.json`

The category applicator now derives output filenames from the checked-in batch ID. New batches add decision ledgers and run sequentially without duplicating the tool.

## Fixed digests

| Data | SHA-256 |
|---|---|
| Source manifest | `c212ecfe662cb76bc5a40061b351af49b75876c4d4aad5036f3e0b41c5c8b04c` |
| Full review queue | `917de3ef2b391f07dd300f66a9ac1d98ad22f9a0ed9b0a33753e9690f321fce6` |
| Full review packs | `57c26478b26aef31f39ce1a086b69e481cc955a4cbe711b863c6620b82a973da` |
| Substring decision ledger | `bc907632f87da3443a4d928972e740a849e8096fb5cd3b2ca5d342e00c982c8e` |
| Category batch 001 decision ledger | `117a32a6fa7d09d49d72e33194fe551fdf58f09dbf6d97f66ed3109d8a0a9386` |
| Category batch 002 decision ledger | `9b91327b4ff3a882b5ae5d1ec97a9f91cfb10277fbafc10b88ef76b41a23f671` |

## Next order

```text
Substring artifacts: 39 reviewed
  -> name/place category batch 001: 20 reviewed
  -> name/place category batch 002: 20 reviewed
  -> remaining suspected category mismatches: 1,250
  -> high-risk external-action candidates: 250
  -> source or license blockers: 1,913
  -> meaning/context evidence, scope tests, Gold cases, and independent holdout
  -> Stage 4 for approved entries only
```

Incorrect candidates will not be retained merely to preserve the 5,000 count, and candidates will not be automatically reclassified. Only fully reviewed entries may enter Stage 4.
