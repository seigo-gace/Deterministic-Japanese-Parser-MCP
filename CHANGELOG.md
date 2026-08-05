# Changelog

このFileは、Public Repositoryで利用者へ影響する変更を記録します。

This file records user-visible changes to the public repository.

## Unreleased

### Added

- Separate English entrypoint in `README_EN.md`, linked from the Japanese `README.md`.
- Public community validation contract in `VALIDATION.md`.
- GitHub Discussion category forms for validation campaigns, validation results, Japanese-language review, environment validation, and evidence review.
- Deterministic context-sensitive sense selection for high-impact polysemous Japanese expressions.
- Sense candidates, evidence, and confidence fields in the Meaning Graph.
- Local omitted-target and zero-object recovery with explicit inference evidence.
- Typed and ordered reference ranking for `前者`、`後者`、typed demonstratives, current mentions, known entities, and conversation context.
- Pragmatic speech acts for polite requests, desires, commitments, refusals, deferrals, concerns, clarification requests, approvals, rejections, and capability questions.
- Discourse edges for cause, contrast, elaboration, justification, sequence, alternatives, and purpose.
- Fail-closed handling for unresolved senses, omitted targets, reported commands, quotations, questions, commitments, desires, and unresolved demonstratives.
- Supported Semantic Quality Contract: 167 cases.
- Independent Semantic Holdout Contract: 130 runtime-independent cases.
- Public security and support policies.
- Public Issue form and Pull Request template.
- Public documentation index and release checklist.
- CI-backed Public Repository Contract that rejects missing public files and private workspace links.
- Repository-level integration test proving that all twelve Open Lexicon runtime shards are preloaded and connected as one 120,000-record dictionary.
- Workflow safety contract preventing the Open Lexicon workflow from committing or pushing generated files back into branches.

### Changed

- The root `README.md` is now Japanese-only and `README_EN.md` is English-only; both provide an explicit language switch at the top.
- External Shields.io status images were removed. Only the repository-native CI badge remains; Python, MCP, runtime model, and license are displayed as text so GitHub mobile clients do not show blank badge areas.
- GitHub Discussions are the public entrypoint for independent validation, uncertain findings, Japanese-language review, environment checks, candidate evidence, questions, and early ideas.
- GitHub Issues are restricted to confirmed, reproducible bugs and regressions that require a fix.
- The public feature-request and usage-question Issue forms were removed; the Issue chooser now routes those users to Discussions.
- Project-control synchronization and CI now validate the Japanese and English READMEs independently.
- The `Compile 120k Open Lexicon` workflow is now read-only: it rebuilds in a temporary directory, compares deterministic output, uploads evidence, and never changes a branch.
- The obsolete `feature/import-all-dictionaries` branch trigger and pending-patch application step were removed.
- Release wheels now contain the compiled Open Lexicon runtime once, instead of packaging both the auditable source snapshot and the compiled runtime copy.
- Public documentation now distinguishes the current 154,921 exact surfaces and 1,711 ambiguous surfaces from historical snapshot values.

### Verified

- Supported semantic profile: **167 / 167**.
- Independent semantic holdout: **130 / 130**.
- Combined supported semantic cases: **297 / 297**.
- Holdout sense selection: **52 / 52**.
- Holdout pragmatics: **28 / 28**.
- Holdout ellipsis resolution: **12 / 12**.
- Holdout discourse relations: **10 / 10**.
- Holdout reference resolution: **8 / 8**.
- Holdout external-action safety: **20 / 20**.
- Macro accuracy and every semantic category exceed the public 95% / 90% thresholds.
- The same contracts are executed against the offline release wheel with the generated 120k lexical snapshot.
- Current Open Lexicon manifest: **120,000 records**, **12 runtime shards**, **154,921 exact surfaces**, **126,936 readings**, and **1,711 ambiguous surfaces**.
- Full record-locator coverage: **120,000 / 120,000**.

## 0.3.1 - 2026-08-04

### Fixed

- Corrected the 120,000-record JMdict import model so one source entry remains one source-traceable runtime record.
- Separated orthographic surfaces from readings.
- Preserved `re_restr` and `re_nokanji` as reading mappings.
- Stopped promoting readings into canonical aliases.
- Isolated open lexical identities into exact-only lookup groups.
- Prevented unrelated substring candidates from leaking into ordinary sentences.
- Prevented containment alone from merging different words.

### Added

- Full-source JMdict audit for 120,000 runtime records.
- Exact lookup verification for 154,918 unique surfaces.
- Ambiguous-surface retention checks for 962 surfaces.
- 20,000 containment precision cases.
- 20,000 sentence substring-pollution cases.
- Open Lexicon Accuracy Contract.

### Verified

- Accuracy errors: `0`.
- Python 3.10 and 3.12 CI.
- 74 offline pytest cases with the generated 120k lexical snapshot.
- 649 Gold Corpus cases.
- 20x dictionary scale tests.
- Persistent local stdio Astera call-through contract.

## Earlier implementation history

Earlier public implementation work is traceable through the merged pull requests:

- PR #1: initial public repository implementation.
- PR #4: deterministic Meaning Graph runtime rebuild.
- PR #5: practical dictionary and Gold Corpus expansion.
- PR #6: comprehensive deterministic Japanese coverage expansion.
- PR #7: open dictionary supply chain completion.
- PR #8: 120k open lexicon accuracy correction and verification.
- PR #9: public repository hardening and public repository contract.

The changelog does not claim a tagged release where no GitHub Release or tag exists.
