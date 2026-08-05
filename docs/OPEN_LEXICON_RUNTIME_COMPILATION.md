# 120,000 Open Lexicon Runtime Compilation

The 12 imported JMdict shards are source records. They are not scanned linearly for every request. GitHub Actions compiles them into deterministic runtime assets.

## Generated data

- orthographic canonical groups
- exact surface → record IDs index
- reading → record IDs and reading restrictions index
- same-surface ambiguity index
- part-of-speech index
- domain index
- usage-label index
- record ID → record shard/line locator
- compact, deterministic record shards
- source and output checksum manifest

## Safety boundary

The compiler preserves lexical identity only. It does not automatically promote definitions, senses, synonyms, intent, tasks, metaphors, pragmatic interpretation, or external actions. Readings remain metadata and are not added as orthographic aliases.

## Execution

```bash
python tools/compile_open_lexicon_runtime.py \
  --input-root dictionaries/system/lexicon.d \
  --output-root dictionaries/system/compiled/open_lexicon \
  --expected-records 120000 \
  --record-shard-size 10000

python tools/validate_compiled_open_lexicon.py \
  --root dictionaries/system/compiled/open_lexicon \
  --expected-records 120000
```

The workflow `.github/workflows/compile-open-lexicon.yml` runs this against the actual 12 shards and commits deterministic compiled assets only after validation passes.
