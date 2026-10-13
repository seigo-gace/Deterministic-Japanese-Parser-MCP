# Source-purpose-first data placement — Design Delta (2026-10-14)

Status: PROPOSED_PR, not adopted main. Owner: DJPMCP comprehension data/DB CU, [Issue #51](https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP/issues/51).
Baseline: `docs/PARSER_ARCHITECTURE.md` §§2,5–9,13,17 and `docs/UNIFIED_SEMANTIC_DATA_PIPELINE.md`; preserve canonical purpose, Source/rights, review and runtime safety.

## Correction from Master

The goal is not to distribute 9,852,513 canonical records among 12 predefined buckets. The goal is to preserve Japanese meaning, intent, structure, context, conditions, exceptions, scope and dependency for downstream AI/translation with deterministic evidence. Existing public source data have already been acquired/processed. Reuse them and determine **what each source field represents, why Japanese reading needs it, how the parser consumes it, and where it belongs**, before deciding its physical/index placement.

An existing lane is a candidate destination, **not an exhaustive ontology and not an automatic acceptance rule**. If no existing responsibility can express a real reading requirement, propose the missing logical responsibility/field/retrieval consumer rather than force-fitting or silently discarding the data. Do not conflate a logical responsibility, a physical DB, a secondary facet, or an existing purpose/source-role mask.

## Mandatory traceability model

For each logical Source and meaningful field family (not only source file name), record:
- `source_id`, immutable source/version/digest, raw→adapter→canonical lineage, input and eligible counts.
- `field_path`, upstream field semantics, explicit example and whether the field has *source-authored meaning*, a reading/structure relation, a ranking hint, or provenance-only evidence. Preserve unknown semantics without inventing them.
- `reading_need`: specific Japanese phenomenon/ambiguity/meaning-preservation failure the field addresses (or `NOT_APPLICABLE/UNKNOWN`).
- `processing_stage` and named consumer (normalization, morphology, multi-lane routing, retrieval, syntax/case, sense/context, document/discourse, MeaningGraph evidence, or action safety); never call an absent consumer implemented.
- `logical_destination`: one or multiple existing lanes/facets, declared auxiliary-only usage, or `NEW_RESPONSIBILITY_CANDIDATE`, with reasons and negative alternatives.
- `field_rights`, `source_evidence`, `provenance`, `review_status`; separate private/review-only/public-runtime eligibility.
- `canonical_count`, `assigned_count`, `retrievable_count`, `actually_consumed_count`, `unmapped_count`, `rejected_count` by stage; each marked measured or UNKNOWN, with manifest/CI/Host artifact identity.
- `semantic_effect`: what parser output field/edge/ambiguity state should differ on a representative Japanese example; and `test_evidence` for an end-to-end assertion.

A source may project into several logical lanes, provided one canonical authority remains. The 12 named lanes stay as the **current baseline**, not a permanently exhaustive list. A Secondary Facet is adequate only when an existing consumer can interpret it without losing reading semantics.

## Gap triage (mutually distinguished, not collapsed into 'unmapped')

1. **MISSING_INPUT**: upstream field/record not present in the processed canonical set → repair source intake/lineage without invented meaning.
2. **MISSING_MAPPING**: canonical evidence is present and existing logical responsibility fits, but assignment is absent/wrong → repair deterministic compiler classification.
3. **MISSING_CONSUMER**: mapping/retrieval exists but downstream parser cannot consume or propagate evidence → repair router, retrieval, resolution or MeaningGraph integration.
4. **MISSING_AUTHORITY**: necessary meaning/rights/field interpretation is not established by a source → retain unresolved/review-only, seek actual authority; no auto-approval.
5. **MISSING_RESPONSIBILITY**: no existing lane/facet and consumer contract can express a genuine independent Japanese-reading use → design a new logical responsibility with explicit input, output, failure behavior and version impact.

Do not interpret a zero lane count as automatic proof of missing source, or a nonzero lane count as runtime quality. J-Ono is one known source-specific defect, not the limit of the whole-source audit. Keep existing J-Ono review gate, unresolved POS/polysemy, and no-auto-promotion controls independent.

## Execution order and acceptance

1. Read current source profiles, compiler assignments, canonical manifest and **actual** Full Build/Audit reports before modifying data. Inventory all registered logical sources (prior pipeline design documents describe 67 inputs/66 logical sources; remeasure Current rather than assume this is still exhaustive).
2. Produce a deterministic **Source × Field × Reading Need × Stage × Destination × Coverage × Runtime × Gap** inventory from existing assets, with evidence pointers and UNKNOWN for inaccessible artifacts; preserve rejected/unmapped field payloads.
3. For each gap, apply the triage above. First use existing source adapter / ledger / canonical / projection / router / reader contracts; do not rebuild all records merely to produce the inventory.
4. For each `MISSING_RESPONSIBILITY` candidate, prove that existing lane/facet cannot express the needed reading behavior. Specify logical interface, example input, expected MeaningGraph effect, data/rights lineage, decoder/router integration, schema/version/bitmask compatibility and rollback. A new lane or physical DB requires evidence and separate compatibility work, not just a label.
5. Implement verified minimal mapping/consumer fixes only after the inventory identifies them. Add positive, ambiguous, absent-rights and negative examples; confirm no unsupported meaning promotion, no semantic_hash drift and no Action safety regression.
6. Validate source conservation and deterministic bundle identity, field-rights/permission, exact retrieval, real parser consumption, meaning-preservation cases, p50/p95/p99 and 0.5s target when production-qualified. Distinguish Source, Test, CI, Host, Runtime and final acceptance.

## Non-goals

No speculative new data harvesting, mandatory Japanese localization of machine-first fields, forced assignment to existing twelve lanes, automatic semantic/POS approval, irreversible replacement of canonical assets, creation of a new large typo DB, runtime LLM inference, or treating documents/green CI as production completion.

## Next executable unit

Generate the initial source-field inventory **from existing profiles + actual build manifests**, identify Source data with `MISSING_MAPPING` / `MISSING_CONSUMER` / `MISSING_RESPONSIBILITY` candidates and implement the first evidence-backed correction. Where Full Build artifacts exist only in Host/Actions, use the already authorized registered read-only route and preserve UNKNOWN until retrieved. Continue original product acceptance after this correction; do not make documentation itself the endpoint.
