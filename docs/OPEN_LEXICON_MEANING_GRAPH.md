# Open Lexicon MeaningGraph Connection

## Stage 3 status

The compiled 120,000-record open lexicon is connected to MeaningGraph as lexical identity nodes.

## Resolution policy

The resolver ranks the already-bounded token candidates using deterministic evidence:

- exact surface, normalized surface, or reading match type
- Sudachi reading agreement
- Sudachi/JMdict part-of-speech family agreement
- JMdict reading restrictions and no-kanji constraints
- a small project-reviewed domain cue map
- complete source provenance

A single candidate is selected directly. Multiple candidates are selected only when the top score reaches the minimum and has a decisive margin. Truncated candidate lists and ties remain ambiguous.

## MeaningGraph output

Each lexical node contains the token span, ranked candidates, scores, evidence, selected record ID when resolved, related proposition/entity/sense IDs, confidence and status.

## Safety boundary

This stage resolves lexical identity only. It does not promote open-lexicon records into senses, synonyms, intents, tasks, pragmatic meanings, or external actions. The separate 5,000 context-candidate collection is not loaded or used.
