# Third-party notices

Program Code in this repository is licensed under [`LICENSE`](LICENSE). Third-party packages, dictionaries, corpora, lexical records, and other imported data keep their own license and attribution requirements; the MIT license for Project Code does not replace those terms.

## License / distribution boundary

| Component / data | Role | How it enters a runtime | Bundled in this repository / wheel | License / attribution boundary |
|---|---|---|---|---|
| SudachiPy | Japanese tokenizer runtime dependency | Installed as a Python dependency | Dependency, not Project-authored Program Code | Upstream package license applies |
| SudachiDict Core | Sudachi tokenizer dictionary | Installed as the declared Sudachi dictionary dependency | External dependency rather than Project-authored dictionary data | Apache License 2.0 as recorded by this Project; upstream component notices continue to apply |
| Project-authored rules, metaphor/pragmatic entries, synonyms, workflows and Gold data | Deterministic parser/default evaluation data | Shipped from the repository/package data | Yes, where selected by packaging configuration | Project-authored material; this section does not relicense third-party material into it |
| JMdict lexical-identity projection | Surface/reading/lexical identity evidence only | Reviewed records under `dictionaries/system/lexicon.d/cc-by-sa/`, then compiled to Open Lexicon runtime | Yes: current runtime projection contains 120,000 records | CC BY-SA 4.0; attribution to the Electronic Dictionary Research and Development Group; source identifier and digest retained |
| Japanese Wiktionary importer input | Candidate dictionary supply source | External acquisition → importer → proposal/review | Raw source is not automatically bundled into runtime dictionaries | Source license/attribution applies to any promoted records; promotion requires license-separated pack + source manifest |
| Wikidata Lexemes importer input | Candidate dictionary supply source | External acquisition → importer → proposal/review | Raw source is not automatically bundled into runtime dictionaries | Source terms apply; review and provenance are required before any promotion |
| SudachiDict source importer input | Candidate dictionary supply/source evidence | External acquisition → importer → proposal/review | Raw source is not automatically promoted | Upstream license/component notices apply to promoted material |
| External corpora / documentation used only as review evidence | Usage/evaluation evidence | Review process only unless a separately licensed import is explicitly approved | Not bundled merely because it was consulted | Corpus/document license, redistribution, privacy and attribution terms remain separate |

**Bundled** means the Project actually distributes the relevant Project package data or compiled runtime projection. **External acquisition** means the Repository may contain tooling or a source definition for obtaining/reviewing material, but that source content is not thereby incorporated into the distributed runtime.

## Runtime dependencies

This project depends on SudachiPy and SudachiDict. SudachiDict is distributed under Apache License 2.0. Dependency installation does not convert those packages into Project-authored MIT Program Code; retain and follow the upstream notices that accompany the installed distribution.

## Project-authored dictionaries

The currently bundled metaphor, pragmatic-expression, intent-rule, synonym, workflow, and Gold data are project-authored curated entries. External corpora and public documentation were used to review usage and terminology; corpus passages and third-party dictionary definitions were not copied into those original packs.

Third-party evidence must not be copied into a Project-authored pack merely to avoid its original license. Provenance and rights are determined by the source material, not by the destination path or generated file format.

## Open dictionary supply chain

The repository includes importers and review tooling for Japanese Wiktionary, Wikidata Lexemes, JMdict, and SudachiDict source data. Importer output and review proposals are not automatically part of the runtime dictionaries.

When reviewed external dictionary records are promoted, they are stored in license-separated packs under `dictionaries/system/lexicon.d/`. Each promoted batch must add a source manifest under `dictionaries/sources/` and a batch notice below containing dataset, version, license, and attribution. The source license continues to govern the imported data; the project's MIT code license does not replace it.

The current runtime includes 120,000 lexical-identity records derived from JMdict. They are stored under `dictionaries/system/lexicon.d/cc-by-sa/` and compiled into `dictionaries/system/compiled/open_lexicon/`. Each record retains the JMdict source identifier, source digest, CC BY-SA 4.0 license, and attribution to the Electronic Dictionary Research and Development Group. No JMdict meaning, pragmatic interpretation, intent, task, or external-action decision is automatically promoted with those lexical records.

## Promotion requirements for new third-party data

A new promoted batch must identify, at minimum:

- dataset/source name and version or immutable source identifier;
- exact license and required attribution;
- whether original source records are redistributed, transformed, or used only as evidence;
- destination license lane under `dictionaries/system/lexicon.d/` or another explicitly documented runtime location;
- source manifest / provenance record and digest;
- whether the material is packaged in the wheel/runtime or requires separate external acquisition;
- restrictions on commercial use, redistribution, derivative data, privacy, or model/training use when applicable.

If the rights cannot be verified, the material must not be promoted into the public runtime distribution.
