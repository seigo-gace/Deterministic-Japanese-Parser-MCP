# Current Context v3 Stage 3 Result

<p align="center">
  <a href="README.md">Japanese</a> ｜ <strong>English</strong>
</p>

## Status

All 5,000 candidates are accounted for in the Stage 3 review queue.

The first review scope, 39 suspected substring artifacts, has also been completed. Thirty-eight entries were excluded from the epistemic candidate set, while `いいかも` was returned to direct-occurrence, meaning, and scope evidence review.

This is not approval completion. Approved entries remain at zero, and no entry has been promoted into the runtime.

## Initial triage result

| Review status | Count |
|---|---:|
| Blocked on source or license | **1,913** |
| High-risk external-action review | **250** |
| Ready for human evidence review | **1,508** |
| Suspected category mismatch | **1,290** |
| Suspected substring artifact | **39** |
| Total | **5,000** |

## After explicit review decisions

| Review status | Count |
|---|---:|
| Blocked on source or license | **1,913** |
| High-risk external-action review | **250** |
| Ready for human evidence review | **1,509** |
| Suspected category mismatch | **1,290** |
| Reviewed and rejected | **38** |
| Remaining suspected substring artifacts | **0** |
| Runtime promotions | **0** |

### First review batch

- Thirty-eight entries such as `かものはし`, `かもしか`, `さかもと`, `何もかも`, and `しかも` were excluded because an embedded string was incorrectly treated as the epistemic marker `かも`.
- `いいかも` can contain a real epistemic use of sentence-final `かも`, so it was retained for direct evidence and scope review rather than approved.
- No decision promotes an entry into Meaning Graph senses, intents, tasks, external actions, or runtime assets.
- The applicator cannot invent decisions. It applies only the checked-in explicit decision ledger.

Decision evidence:

- `research/context_collection/stage3_decisions/epistemic-substring-decisions-v1.jsonl`
- `reports/context-v3-stage3/decision-summary.json`
- `reports/context-v3-stage3/runtime-boundary-after-decisions.json`

## Main findings

- Every candidate still requires direct occurrence evidence.
- 1,913 records have an unresolved license.
- 1,695 records lack evidence for their assigned category.
- 500 records have a category and feature-type mismatch.
- 210 records may be names or places rather than context features.
- The 39 initially suspected substring artifacts now have no unreviewed remainder.
- 800 records require external-action safety review.

Examples include `和田` under dialect candidates and `かものはし`, `さかもと`, and `何もかも` under epistemic candidates.

## Review packs and artifacts

The 5,000 records are split into **260 packs** of at most 20 entries.

Each Stage 3 GitHub Actions run generates:

- `review-queue.jsonl`;
- `review-packs.jsonl`;
- `review-pack-index.json`;
- `summary.json`;
- `runtime-boundary.json`;
- `applied-decisions.jsonl`;
- `post-decision-queue.jsonl`;
- `decision-summary.json`;
- `runtime-boundary-after-decisions.json`.

## Fixed digests

| Data | SHA-256 |
|---|---|
| Source manifest | `c212ecfe662cb76bc5a40061b351af49b75876c4d4aad5036f3e0b41c5c8b04c` |
| Full review queue | `917de3ef2b391f07dd300f66a9ac1d98ad22f9a0ed9b0a33753e9690f321fce6` |
| Full review packs | `57c26478b26aef31f39ce1a086b69e481cc955a4cbe711b863c6620b82a973da` |
| Substring decision ledger | `bc907632f87da3443a4d928972e740a849e8096fb5cd3b2ca5d342e00c982c8e` |
| Post-decision queue | `233c6dd096f325e2e5ee1c3830fc266bfaffc8fd2826c0dd5b53efff476ed764` |

## Next order

```text
Substring artifacts: 39 reviewed
  -> suspected category mismatches: 1,290
  -> high-risk external-action candidates: 250
  -> source or license blockers: 1,913
  -> meaning and context evidence
  -> positive, negative, boundary, quotation, question, hypothesis, and hearsay tests
  -> Gold cases and independent holdout
  -> Stage 4 for approved entries only
```

Incorrect candidates will not be retained merely to preserve the 5,000 count. Only reviewed candidates with complete evidence, tests, holdout coverage, and safety approval may enter Stage 4.
