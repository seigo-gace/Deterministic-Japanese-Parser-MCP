# Source Map / 主要実装案内

Version 1.0 — 2026-09-26

| Path | 責務 |
|---|---|
| `src/deterministic_japanese_parser_mcp/server.py` | stdio MCP / Tool schema / response cache / prewarm |
| `src/deterministic_japanese_parser_mcp/http_server.py` | Streamable HTTP MCP / REST / auth / health |
| `src/deterministic_japanese_parser_mcp/engine.py` | 全解析pipelineの統合 |
| `src/deterministic_japanese_parser_mcp/models.py` | Pydantic input/output contract |
| `src/deterministic_japanese_parser_mcp/reading_runtime.py` | 述語項・scope・attribution・discourse読解 |
| `src/deterministic_japanese_parser_mcp/semantic_enrichment.py` | 意味補強 |
| `src/deterministic_japanese_parser_mcp/semantic_data_runtime.py` | compiled semantic data runtime |
| `src/deterministic_japanese_parser_mcp/lexical_graph.py` | lexical graph enrichment |
| `src/deterministic_japanese_parser_mcp/language_features.py` | compiled language-feature runtime |
| `src/deterministic_japanese_parser_mcp/language_feature_refinement.py` | language-feature統合 / Fail Closed補強 |
| `src/deterministic_japanese_parser_mcp/anaphora.py` | 照応・指示解決 |
| `src/deterministic_japanese_parser_mcp/graph_guard.py` | External Action Guard |
| `src/deterministic_japanese_parser_mcp/graph_contradictions.py` | Graph上の矛盾検出 |
| `src/deterministic_japanese_parser_mcp/task_graph.py` | Action Task Graph |
| `src/deterministic_japanese_parser_mcp/low_latency_client.py` | schema-safe低遅延MCP client |
| `dictionaries/` | System/User/compiled dictionary and semantic runtime data |
| `scripts/` | benchmark / quality / performance / deployment contracts |
| `tools/` | dictionary compile / validation / import / review tooling |
| `tests/` | unit / integration / E2E / regression / supply-chain検証 |
| `.github/workflows/ci.yml` | Public CI Gate |

## Responsibility Boundaries

### Reading first

`engine.py` coordinates deterministic reading before downstream TaskGraph / external-action decisions. Ordinary descriptive text must not be promoted into an executable instruction without evidence.

### MeaningGraph authority

MeaningGraph is the structured semantic source of truth. Compatibility intent/task views must not silently replace it.

### TaskGraph downstream

TaskGraph is derived after reading. It represents actionable structure and constraints; it is not the source of Japanese meaning.

### Graph Guard

External Action safety is evaluated after semantic/task construction and remains Fail Closed when material ambiguity, contradiction, unresolved reference, unsupported behavior, or deadline failure remains.
