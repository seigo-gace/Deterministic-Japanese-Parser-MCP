# Changelog

このFileは、Public Repositoryで利用者へ影響する変更を記録します。

This file records user-visible changes to the public repository.

## Unreleased

### Added

- Public security and support policies.
- Public Issue forms and Pull Request template.
- Public documentation index and release checklist.
- CI-backed Public Repository Contract that rejects missing public files and private workspace links.

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

The changelog does not claim a tagged release where no GitHub Release or tag exists.