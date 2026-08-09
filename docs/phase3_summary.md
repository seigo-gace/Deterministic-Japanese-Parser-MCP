# Phase 3-2 — 文章全体の要旨抽出（R-15）

Status: **DESIGN / RED PREPARATION**

この文書は Phase 3-1 の `ParagraphStructure` を入力として、文章全体の要旨を決定論的に抽出する Phase 3-2 の実装設計である。生成AI・LLM・外部APIは使用しない。

## 1. Purpose

Phase 3-1 が確定した段落構造と各 `ParagraphFrame.topic_sentence` を利用し、文章全体の主要主張を1つの要旨候補として選択する。十分な根拠がない場合は推測せず `AMBIGUOUS` を返す。

## 2. Input

入力は `ParagraphStructure` とする。

利用する既存情報:

- `ParagraphStructure.paragraphs`
- `ParagraphStructure.ambiguity_flag`
- `ParagraphFrame.topic_sentence`
- `ParagraphFrame.confidence`
- 段落順序

Phase 3-1 が段落を確定できず `paragraphs=[]` または `ambiguity_flag=True` を返した場合、Phase 3-2 が独自に段落境界を推測してはならない。この場合の要旨Statusは `AMBIGUOUS` とする。

## 3. Deterministic processing

### 3.1 Topic sentence collection

1. `paragraphs` を原文順に走査する。
2. `topic_sentence` が存在する段落だけを要旨候補集合へ入れる。
3. 空文字・欠落値は候補にしない。
4. 候補には本文、段落index、段落confidence、位置区分を保持する。

### 3.2 Position weighting

文章構造上の位置だけを決定論的な優先Signalとして使用する。

- 最初の段落: high priority（導入・主題提示候補）
- 最後の段落: high priority（結論・総括候補）
- 中間段落: lower priority（補足・展開候補）

単一段落の場合は最初と最後を重複加点せず、1候補として扱う。

実装時のBaseline weightは以下とする。

- first: `1.00`
- last: `0.90`
- middle: `0.50`

候補scoreは `position_weight * paragraph_confidence` とし、0.0〜1.0へclampする。同点時は原文順を安定Tie-breakに使用するが、同点だからといって内容上の不確実性を隠してはならない。

## 4. Summary decision

### DETERMINED

以下をすべて満たす場合だけ `DETERMINED` とする。

1. 有効なtopic sentence候補が1件以上ある。
2. `ParagraphStructure` 自体がambiguousではない。
3. 最上位候補が他候補から十分に分離している、または候補が1件だけである。

最上位候補の `topic_sentence` を `summary_text` とする。Phase 3-2では新しい文章を生成・言換えしない。

### AMBIGUOUS

以下のいずれかなら `AMBIGUOUS` とする。

- `ParagraphStructure` がない。
- `paragraphs` が空。
- `ambiguity_flag=True`。
- 有効な `topic_sentence` がない。
- 上位候補を一意に決定できない。

複数候補の上位score差が `0.20` 未満の場合は、一意性不足として `AMBIGUOUS` とする。AMBIGUOUS時は `summary_text` を確定せず、候補一覧と根拠段落indexだけを返す。

## 5. Confidence

`confidence` は0.0〜1.0の範囲とする。

- DETERMINED: 選択候補のscoreを基礎に、次点との差を分離度として反映する。
- 単一候補: その候補scoreを使用する。
- AMBIGUOUS: 0.0〜0.79の範囲に留め、確定結果と同等に扱わない。
- 入力なし / 段落なし / topic sentenceなし: `0.0`。

数式は実装時に固定し、同じ入力から常に同じ値を返すこと。乱数、時刻、外部通信、生成AI出力を使用しない。

## 6. Output contract

Phase 3-2実装時に `ReadingAnalysis` へ要旨結果を追加する。

想定Field:

- `summary_text: str | None`
- `confidence: float`（0.0〜1.0）
- `status: DETERMINED | AMBIGUOUS`
- `candidates: list[str]`
- `source_paragraph_indices: list[int]`
- `method: topic_sentence_aggregation`

具体的なModel class名と最終Field名は実装Change Unitで既存Pydantic Model規約へ合わせて確定する。

## 7. Integration points

現行Branchの実装では、`src/deterministic_japanese_parser_mcp/models.py` に `ParagraphFrame`、`ParagraphStructure`、`ReadingAnalysis.paragraph_structure` が存在する。Summary用Modelは `ParagraphStructure` と `ReadingAnalysis` の近傍へ追加し、`ReadingAnalysis` から参照する。

`src/deterministic_japanese_parser_mcp/reading_runtime.py` は `ParagraphFrame` / `ParagraphStructure` / `ReadingAnalysis` を使用してPhase 3-1の段落解析を構築している。Phase 3-2実装ではParagraphStructure確定後に純粋なルール関数として要旨抽出を呼び出し、その結果だけを `ReadingAnalysis` へ格納する。

この準備Change Unitでは上記2 Source Fileは変更しない。

## 8. RED tests

`tests/test_summary.py` に以下の4ケースをRED skeletonとして置く。

- `test_single_paragraph_summary`
- `test_multi_paragraph_summary`
- `test_ambiguous_summary`
- `test_summary_confidence`

このCommitでは要旨抽出本体を実装しないため、これらは意図的にFAILする。P0 Dictionary Data PipelineがGreenになった後、別Change UnitでSource実装とRED→GREENを行う。

## 9. Non-goals / boundaries

- AI / LLMによる要約生成をしない。
- 外部APIへ通信しない。
- Phase 3-1が確定していない段落境界を補完しない。
- 新しい論証構造・Coreference・背景知識推論を追加しない。
- `needs-evidence` の状態を変更しない。
- 236MB分割Ledgerを扱わない。
- PR #27をMergeしない。
- main/masterへPushしない。
