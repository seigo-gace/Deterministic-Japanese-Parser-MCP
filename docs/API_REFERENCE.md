# API Reference / 公開Interface仕様

Version 1.0 — 2026-09-26

## MCP Tool

Tool name:

```text
analyze_japanese
```

MCP server name:

```text
deterministic-japanese-parser
```

Current package/server version:

```text
0.4.0
```

The server publishes `AnalyzeRequest.model_json_schema()` as the input schema and `AnalyzeResponse.model_json_schema()` as the output schema.

## AnalyzeRequest

| Field | Required | Default | 内容 |
|---|---:|---|---|
| `original_text` | Yes | - | 解析する日本語。空文字列不可 |
| `conversation_context` | No | `[]` | 照応・文脈解決に使う直前発話 |
| `known_entities` | No | `[]` | 呼び出し側が既知として渡す対象 |
| `protected_elements` | No | `[]` | 変更禁止対象 |
| `social_context` | No | empty model | speaker/addressee/relation/setting等 |
| `discourse_state` | No | `{}` | 呼び出し側が保持する談話状態 |
| `execution_mode` | No | `analysis` | `analysis` / `comparison` / `planning` / `external_action` |
| `analysis_depth` | No | `auto` | `auto` / `fast` / `deep` |
| `deadline_ms` | No | `50` | 1〜60000ms。Engine hard deadline以下へclamp |

## AnalyzeResponse

主要Field:

| Field | 内容 |
|---|---|
| `overall_status` | `COMPLETE` / `PARTIAL` / `FAILED` |
| `execution_allowed` | External Actionへ進めるか |
| `blocked_reasons` | Fail Closed理由 |
| `original_text` | 入力原文 |
| `normalized_text` | 正規化結果 |
| `analysis_path` | `FAST` / `DEEP` / `FAILED` |
| `tokens` | Token情報 |
| `meaning_graph` | 読解の中心Graph |
| `task_graph` | Action Task Graph |
| `intents` | compatibility intent view |
| `metaphors` | 比喩・慣用表現解析 |
| `references` | 照応解析 |
| `tasks` | compatibility task view |
| `ambiguities` | 未解決の曖昧性 |
| `missing_information` | 判断に不足する情報 |
| `contradictions` | 矛盾・衝突 |
| `unsupported_elements` | 未対応要素 |
| `timeouts` | deadline関連情報 |
| `versions` | Runtime / dictionary等のVersion情報 |
| `metrics` | phase latency / deadline / cache等 |

`MeaningGraph.semantic_hash` はMeaning Graph内容の再現可能な識別に使われます。

## MCP CallToolResult

`analyze_japanese` のTool Callは2種類の表現を返します。

1. `structuredContent`: complete structured parser response
2. text content: compact operational summary

text summaryには現在、次が含まれます。

```text
overall_status
execution_allowed
proposition_count
predicate_frame_count
scope_operator_count
action_task_count
semantic_hash
```

## Python API

```python
from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine

response = ParserEngine().analyze(
    AnalyzeRequest(
        original_text="UIは維持する。APIだけ変更しろ。",
        protected_elements=["UI"],
        execution_mode="external_action",
    )
)
```

Direct backward-compatible entrypoint `analyze_japanese(...)` も公開されています。

## HTTP Runtime

Entrypoint:

```text
djpmcp-http
```

Routes:

| Route | 用途 |
|---|---|
| `/mcp` | Streamable HTTP MCP |
| `POST /v1/analyze` | Parser REST interface |
| `/healthz` | Health |
| `/readyz` | Readiness |

`/healthz` と `/readyz` 以外はRuntime Authentication対象です。

ProductionのSecurity / Gateway境界は[`PRODUCTION_HTTP_DEPLOYMENT.md`](PRODUCTION_HTTP_DEPLOYMENT.md)を参照してください。

## Status Semantics

### COMPLETE

必要な読解構造が得られ、重要な未解決要素・矛盾・timeout等が残っていない状態。

### PARTIAL

有効な解析結果は存在するが、reference / ambiguity / contradiction / unsupported / timeout等が残る状態。

### FAILED

Meaning Graphとして必要な構造を構築できなかった状態。

特に`execution_mode="external_action"`では、`overall_status`だけでなく`execution_allowed`と`blocked_reasons`を必ず確認してください。
