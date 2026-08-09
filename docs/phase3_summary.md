# Phase 3-2 — 文章全体の要旨抽出（R-15）

Status: **IMPLEMENTED / CI GREEN**

この文書は Phase 3-1 の `ParagraphStructure` を入力として、文章全体の要旨を決定論的に抽出する Phase 3-2 の実装仕様である。生成AI・LLM・外部APIは使用しない。

## 1. Purpose

Phase 3-1 が確定した段落構造と各 `ParagraphFrame.topic_sentence` を利用し、文章全体の主要主張を要旨候補として選択する。十分な根拠がない場合は推測せず `AMBIGUOUS` を返す。

## 2. Input

入力は `ParagraphStructure | None` とする。

利用する情報:

- `ParagraphStructure.paragraphs`
- `ParagraphStructure.ambiguity_flag`
- `ParagraphFrame.topic_sentence`
- `ParagraphFrame.confidence`
- 段落順序

Phase 3-1 が段落を確定できず `paragraphs=[]` または `ambiguity_flag=True` を返した場合、Phase 3-2 が独自に段落境界を推測してはならない。この場合の要旨Statusは `AMBIGUOUS` とする。

## 3. Deterministic processing

### 3.1 Topic sentence collection

1. `paragraphs` を原文順に走査する。
2. `topic_sentence` が存在する段落だけを候補集合へ入れる。
3. 欠落した `topic_sentence` は候補にしない。
4. 各候補には本文、段落index、scoreを保持する。

### 3.2 Position weighting

現行 `DeterministicReadingRuntime._extract_summary()` の実装は、段落位置を次の固定weightへ変換する。

- 単一段落、または最初の段落: `1.00`
- 最後の段落: `0.75`
- 中間段落: `0.50`

候補scoreは `position_weight * paragraph_confidence` とし、0.0〜1.0へclampする。

候補は `score` 降順で安定Sortし、同scoreの場合は段落index昇順をTie-breakに使用する。乱数、時刻、外部通信、生成AI出力は使用しない。

> 実装同期注記: 現行Runtimeは `1.0 / (idx + 1)` 方式ではなく、上記 `1.00 / 0.75 / 0.50` の固定位置weightを使用している。本書はGitHub実装事実との同期を目的として、この現行値を記録する。

## 4. Summary decision

### DETERMINED

以下を満たす場合に `DETERMINED` とする。

1. `ParagraphStructure` が存在する。
2. `ambiguity_flag=False`。
3. 有効な `topic_sentence` 候補が1件以上ある。
4. 候補が複数ある場合、最上位scoreと次点scoreの差が `0.20` 以上である。

最上位候補の `topic_sentence` をそのまま `summary_text` とする。Phase 3-2では新しい文章を生成・言換えしない。

### AMBIGUOUS

以下のいずれかなら `AMBIGUOUS` とする。

- `ParagraphStructure` がない。
- `paragraphs` が空。
- `ambiguity_flag=True`。
- 有効な `topic_sentence` がない。
- 上位2候補のscore差が `0.20` 未満。

上位score差が `0.20` 未満の場合、上位最大3候補を `candidates` に保持し、その段落indexを `source_paragraph_indices` に保持する。`summary_text` は確定しない。

## 5. Confidence

`confidence` は0.0〜1.0の範囲へclampする。

- 入力なし / 段落なし / ambiguous paragraph structure / topic sentenceなし: `0.0`
- AMBIGUOUS（上位差 < 0.20）: `diff + 0.5`
- DETERMINED: `best_score + 0.5`

同じ入力から常に同じ値を返す。

## 6. Output contract

`ReadingAnalysis.summary` に `SummaryResult | None` を保持する。

`SummaryResult`:

- `summary_text: str | None`
- `confidence: float`（0.0〜1.0）
- `status: "DETERMINED" | "AMBIGUOUS"`
- `candidates: list[str] | None`
- `source_paragraph_indices: list[int]`
- `method: "topic_sentence_aggregation"`

実装は既存Model規約に合わせてPydantic `BaseModel` を使用する。

## 7. Integration points

- `src/deterministic_japanese_parser_mcp/models.py`
  - `SummaryResult` を `ParagraphStructure` 近傍に定義。
  - `ReadingAnalysis.summary` を追加。
- `src/deterministic_japanese_parser_mcp/reading_runtime.py`
  - `DeterministicReadingRuntime._extract_summary()` を実装。
  - `paragraph_structure` 検出後に `_extract_summary(paragraph_structure)` を呼び出し、`ReadingAnalysis.summary` へ格納。
- `tests/test_summary.py`
  - Phase 3-2の4 TestをGREEN Assertionとして保持。

## 8. Validation

Phase 3-2実装Head `2782dcdf948b0aa7248f82cafb0d1d309d586134` に対する CI Run `31321756829` で、Python 3.10 / 3.12 の両JobがSuccessした。

- Python 3.10: `189 passed`
- Python 3.12: `189 passed`
- Performance Contract: Success
- Astera latency target 10ms / hard limit 50ms: Success
- `compileall`: Success

P0 Dictionary Data Pipelineは別Workflowとして扱い、Phase 3-2の実装・CI結果と混同しない。

## 9. Non-goals / boundaries

- AI / LLMによる要約生成をしない。
- 外部APIへ通信しない。
- Phase 3-1が確定していない段落境界を補完しない。
- R-16論証構造をPhase 3-2へ混入しない。
- `needs-evidence` の状態を変更しない。
- 236MB分割Ledgerを扱わない。
- PR #27をMergeしない。
- main/masterへPushしない。
