# Current Context v3 Stage 3 Result

<p align="center">
  <a href="README.md">Japanese</a> ｜ <strong>English</strong>
</p>

## Status

All 5,000 candidates are accounted for in the Stage 3 review queue.

- Batch 1 reviewed all 39 suspected substring artifacts: 38 rejected and `いいかも` returned to evidence review.
- Batch 2 reviewed the first 20 name-or-place suspects against their source YAML: 10 modality mismatches rejected and 10 honorific-related entries retained for evidence review.

Approved entries remain at zero. Runtime promotions and automatic reclassification remain at zero.

## Initial triage result

| Review status | Count |
|---|---:|
| Blocked on source or license | **1,913** |
| High-risk external-action review | **250** |
| Ready for human evidence review | **1,508** |
| Suspected category mismatch | **1,290** |
| Suspected substring artifact | **39** |
| Total | **5,000** |

## Current status after explicit decisions

| Review status | Count |
|---|---:|
| Blocked on source or license | **1,913** |
| High-risk external-action review | **250** |
| Ready for human evidence review | **1,519** |
| Suspected category mismatch | **1,270** |
| Reviewed and rejected | **48** |
| Runtime promotions | **0** |

## Review batch 1

- Thirty-eight lexical false positives were excluded from the epistemic candidate set.
- `いいかも` was retained for direct occurrence, meaning, and scope review.

## Review batch 2: category name/place batch 001

The original gloss, `source_pos`, and source tags were inspected for each entry.

- **Rejected modality mismatches:** `GHQ/SCAP`, `コモロ`, `京女`, `マスティク島`, `GHQ`, `こどもの日`, `メイ`, `メイヨー`, `ダマスカス`, `ラーマーヤナ`.
- **Retained for honorific evidence review:** `入道前太政大臣`, `後京極摂政前太政大臣`, `揚子`, `お釈迦さま`, `よびすて`, `仲尼`, `法性寺入道前関白太政大臣`, `儀同三司母`, `後徳大寺左大臣`, `かわらのさだいじん`.
- The modality entries are organizations, countries, places, a holiday, a personal name, a work title, or a demonym, not modality functions.
- The honorific entries may encode courtesy titles, courtesy names, honorific morphology, or honorific omission. They remain unapproved pending direct evidence, current-use, scope, and boundary review.
- No entry was automatically moved to another category or promoted into Meaning Graph, intent, task, external action, or runtime data.

## Decision evidence

- `research/context_collection/stage3_decisions/epistemic-substring-decisions-v1.jsonl`
- `research/context_collection/stage3_decisions/category-name-place-batch-001.jsonl`
- `tools/apply_context_v3_stage3_decisions.py`
- `tools/apply_context_v3_stage3_category_decisions.py`
- `reports/context-v3-stage3/decision-summary.json`
- `reports/context-v3-stage3/category-batch-001-summary.json`
- `reports/context-v3-stage3/runtime-boundary-after-category-batch-001.json`

## Main findings

- Every candidate still requires direct occurrence evidence.
- 1,913 records have unresolved source or license blockers.
- 1,695 records lack evidence for their assigned category.
- 500 records have category and feature-type mismatch signals.
- The initial name-or-place suspect set contains 210 entries; 190 remain unreviewed after batch 001.
- 800 records require external-action safety review.

## Fixed digests

| Data | SHA-256 |
|---|---|
| Source manifest | `c212ecfe662cb76bc5a40061b351af49b75876c4d4aad5036f3e0b41c5c8b04c` |
| Full review queue | `917de3ef2b391f07dd300f66a9ac1d98ad22f9a0ed9b0a33753e9690f321fce6` |
| Full review packs | `57c26478b26aef31f39ce1a086b69e481cc955a4cbe711b863c6620b82a973da` |
| Substring decision ledger | `bc907632f87da3443a4d928972e740a849e8096fb5cd3b2ca5d342e00c982c8e` |
| Category batch 001 decision ledger | `117a32a6fa7d09d49d72e33194fe551fdf58f09dbf6d97f66ed3109d8a0a9386` |

## Next order

```text
Substring artifacts: 39 reviewed
  -> name/place category batch 001: 20 reviewed
  -> remaining suspected category mismatches: 1,270
  -> high-risk external-action candidates: 250
  -> source or license blockers: 1,913
  -> meaning/context evidence, scope tests, Gold cases, and independent holdout
  -> Stage 4 for approved entries only
```

Incorrect candidates will not be retained merely to preserve the 5,000 count, and candidates will not be automatically reclassified. Only fully reviewed entries may enter Stage 4.
