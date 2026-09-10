# Third-party notices

## Runtime dependencies

This project depends on SudachiPy and SudachiDict. SudachiDict is distributed under Apache License 2.0.

## Project-authored dictionaries

The currently bundled metaphor, pragmatic-expression, intent-rule, synonym, workflow, and Gold data are project-authored curated entries. External corpora and public documentation were used to review usage and terminology; corpus passages and third-party dictionary definitions were not copied into those original packs.

## Open dictionary supply chain

The repository includes importers and review tooling for Japanese Wiktionary, Wikidata Lexemes, JMdict, and SudachiDict source data. Importer output and review proposals are not automatically part of the runtime dictionaries.

When reviewed external dictionary records are promoted, they are stored in license-separated packs under `dictionaries/system/lexicon.d/`. Each promoted batch must add a source manifest under `dictionaries/sources/` and a batch notice below containing dataset, version, license, and attribution. The source license continues to govern the imported data; the project's MIT code license does not replace it.

The current runtime includes 120,000 lexical-identity records derived from JMdict. They are stored under `dictionaries/system/lexicon.d/cc-by-sa/` and compiled into `dictionaries/system/compiled/open_lexicon/`. Each record retains the JMdict source identifier, source digest, CC BY-SA 4.0 license, and attribution to the Electronic Dictionary Research and Development Group. No JMdict meaning, pragmatic interpretation, intent, task, or external-action decision is automatically promoted with those lexical records.
