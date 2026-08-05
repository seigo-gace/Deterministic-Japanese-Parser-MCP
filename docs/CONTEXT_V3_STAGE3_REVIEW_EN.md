# Context v3 Stage 3 Review

<p align="center">
  <a href="CONTEXT_V3_STAGE3_REVIEW.md">Japanese</a> ｜ <strong>English</strong>
</p>

## Status

The 5,000 Context v3 records have completed candidate collection and candidate generation. They have not completed evidence review.

Stage 3 reviews:

- direct occurrence evidence and provenance;
- meaning and usage context;
- category accuracy;
- substring-derived false candidates;
- names, places, and ordinary lexemes misclassified as context features;
- reading and variants;
- license and redistribution terms;
- positive, negative, and boundary cases;
- quotation, negation, questions, hypotheses, and hearsay;
- external-action risk;
- independent human judgment.

No candidate may be promoted automatically into a resolved Meaning Graph sense, intent, task, or external action.

## Audit of PR #11 and PR #15

PR #11 connected the 120,000-record lexical runtime to the parser and lexical Meaning Graph.

PR #15 added the 5,000 Context v3 candidates, but its change scope also contained runtime data, indexes, workflows, and reports originating from the PR #11 work. The workflows at that point could also commit and push generated changes back into branches.

PR #20 separated and verified the 120k runtime and removed branch-mutating behavior from that workflow. Stage 3 now resumes independently from the corrected main branch.

## Canonical Stage 3 input

```text
research/context_collection/expansion_v3/
├── manifest.json
└── 5,000 YAML records under ten category directories
```

`all_entries.jsonl` and `all_entries.csv` remain convenience mirrors. Stage 3 does not use them as canonical inputs; it validates the manifest and all 5,000 YAML records directly.

## Deterministic triage

`tools/review_context_v3_stage3.py` accounts for every candidate and produces:

```text
summary.json
review-queue.jsonl
review-packs.jsonl
runtime-boundary.json
```

It flags source and license gaps, category mismatches, substring artifacts, name/place candidates, noisy source metadata, external-action risk, and direct-evidence requirements. Review packs contain at most 20 entries.

The tool does not approve, reject, invent meanings, copy proprietary definitions, or promote runtime data.

## Completion boundary

Stage 3 is complete only after human decisions and all required evidence, context, license, examples, collision checks, safety review, Gold cases, independent holdout, and final approval are present.

Stage 4 may compile only the candidates that pass this boundary.
