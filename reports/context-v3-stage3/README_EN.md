# Current Context v3 Stage 3 Result

<p align="center">
  <a href="README.md">Japanese</a> ｜ <strong>English</strong>
</p>

## Status

All 5,000 candidates are accounted for in the Stage 3 review queue.

This is not approval completion. Approved entries remain at zero, and no entry has been promoted into the runtime.

## Result

| Review status | Count |
|---|---:|
| Blocked on source or license | **1,913** |
| High-risk external-action review | **250** |
| Ready for human evidence review | **1,508** |
| Suspected category mismatch | **1,290** |
| Suspected substring artifact | **39** |
| Total | **5,000** |

## Main findings

- Every candidate still requires direct occurrence evidence.
- 1,913 records have an unresolved license.
- 1,695 records lack evidence for their assigned category.
- 500 records have a category and feature-type mismatch.
- 210 records may be names or places rather than context features.
- 39 records appear to be substring-derived false epistemic candidates.
- 800 records require external-action safety review.

Examples include `和田` under dialect candidates and `かものはし`, `さかもと`, and `何もかも` under epistemic candidates.

## Review packs

The 5,000 records are split into **260 packs** of at most 20 entries.

Each Stage 3 GitHub Actions run generates:

- `review-queue.jsonl`;
- `review-packs.jsonl`;
- `review-pack-index.json`;
- `summary.json`;
- `runtime-boundary.json`.

## Fixed digests

| Data | SHA-256 |
|---|---|
| Source manifest | `c212ecfe662cb76bc5a40061b351af49b75876c4d4aad5036f3e0b41c5c8b04c` |
| Full review queue | `917de3ef2b391f07dd300f66a9ac1d98ad22f9a0ed9b0a33753e9690f321fce6` |
| Full review packs | `57c26478b26aef31f39ce1a086b69e481cc955a4cbe711b863c6620b82a973da` |

Incorrect candidates will not be retained merely to preserve the 5,000 count. Only human-reviewed candidates with complete evidence, tests, holdout coverage, and safety approval may enter Stage 4.
