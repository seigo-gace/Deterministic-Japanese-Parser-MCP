# Configuration Reference / 設定リファレンス

Version 1.0 — 2026-09-26

この文書はDeterministic Japanese Parser MCPのRuntime設定をまとめます。READMEはQuick Startに集中し、詳細設定はこの文書をAuthorityとします。

## Parser Engine

| Environment variable | Default | 内容 |
|---|---:|---|
| `DJPMCP_MAX_INPUT_LENGTH` | `20000` | 入力最大文字数 |
| `DJPMCP_MAX_CONTEXT_ITEMS` | `20` | 会話Context最大件数 |
| `DJPMCP_MAX_CANDIDATES` | `8` | 候補上限 |
| `DJPMCP_REGEX_TIMEOUT_MS` | `25` | regex timeout |
| `DJPMCP_TARGET_LATENCY_MS` | `10` | 目標latency |
| `DJPMCP_HARD_DEADLINE_MS` | `50` | Runtime hard deadline |
| `DJPMCP_MAX_GRAPH_NODES` | `512` | Graph node上限 |
| `DJPMCP_MAX_SCOPE_EDGES` | `1024` | scope edge上限 |
| `DJPMCP_LOG_PATH` | `logs/parser.jsonl` | PARTIAL/FAILED診断log |
| `DJPMCP_SYSTEM_DICT_DIR` | bundled system dict | system dictionary root |
| `DJPMCP_USER_DICT_DIR` | bundled user dict | user dictionary root |
| `DJPMCP_SEMANTIC_DATA_RUNTIME_DIR` | unset | semantic runtime root override |

起動時Validationでは、`target_latency_ms >= 1`、`hard_deadline_ms >= target_latency_ms`、Graph limitsが最低値以上であることを確認します。

## HTTP Runtime

| Environment variable | Default | 内容 |
|---|---|---|
| `DJPMCP_HTTP_HOST` | `127.0.0.1` | bind host |
| `DJPMCP_HTTP_PORT` | `8765` | port |
| `DJPMCP_HTTP_WORKERS` | `1` | Uvicorn workers |
| `DJPMCP_HTTP_API_KEY` | unset | Runtime API Key |
| `DJPMCP_HTTP_ALLOW_UNAUTHENTICATED` | `false` | 認証なし起動を明示許可 |
| `DJPMCP_HTTP_MAX_BODY_BYTES` | `1048576` | request body上限 |
| `DJPMCP_HTTP_ALLOWED_ORIGINS` | empty | CORS許可origin CSV |
| `DJPMCP_HTTP_ALLOWED_HOSTS` | loopback系 | Transport Security許可host CSV |

HTTP Production境界は[`PRODUCTION_HTTP_DEPLOYMENT.md`](PRODUCTION_HTTP_DEPLOYMENT.md)を参照してください。

## Semantic Runtime Root

Runtimeは次の優先順位でSemantic Data Rootを解決します。

1. `DJPMCP_SEMANTIC_DATA_RUNTIME_DIR`
2. `compiled/canonical_dictionary_runtime` が有効なら使用
3. `compiled/semantic_data`

この順序により、内部正本・公開可能Data・Runtime projectionを混同しない設計を維持します。

## Performance Contract

`DJPMCP_TARGET_LATENCY_MS=10` と `DJPMCP_HARD_DEADLINE_MS=50` はProjectのPerformance Contractと整合させて管理します。Runtime設定を変更して性能劣化を隠すことを目的に使用してはいけません。

詳細は[`PERFORMANCE_AND_RELEASE_CONTRACT.md`](PERFORMANCE_AND_RELEASE_CONTRACT.md)を参照してください。
