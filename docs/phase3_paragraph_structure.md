# Phase 3｜Paragraph Structure（R-14）設計

## 1. Decision Source / Scope

この文書は Notion 正本 `02｜正本｜現在仕様` の **R-14** を実装へ接続するための初回設計である。

R-14 が要求する結果は、段落単位の **中心テーマ、中心文・支持文、段落の役割、段落間関係、一般論／具体例、問題／原因／対策、反論／限定** の構造化である。

本 Change Unit では設計と最初の RED Test までを対象とし、Paragraph Runtime 自体は実装しない。R-15 の文章全体要旨、R-16 以降の論証・資料統合・批判的読解も実装対象外とする。

## 2. Invariants

- 原文 `original_text` は変更しない。
- Paragraph / Sentence は必ず `OriginalSpan(start, end, source_text)` へ追跡できるようにする。
- 空行等の明示境界がない入力を、推測だけで複数段落へ分割しない。
- 中心文・役割・段落間関係は Evidence があるものだけ `RESOLVED` にし、判定不能時は候補または `INSUFFICIENT / AMBIGUOUS` を保持する。
- 中心テーマを自由生成テキストで捏造しない。既存 Lexical / Proposition / Discourse Evidence から追跡可能な Candidate として扱う。
- Paragraph Structure は `MeaningGraph.reading_analysis` の一部とし、別の意味正本を作らない。
- 同一入力・同一 Context・同一 Rule/Data Version から同一構造を返す。

## 3. Paragraph boundary

### 3.1 Primary boundary

初期実装では、原文中の **空行を含む明示的な段落区切り**を Paragraph Boundary とする。

- `\n\n`、`\r\n\r\n`、空白だけの行を挟む改行を同じ境界種別として検出する。
- 境界検出時に正規化した補助文字列を用いても、保存する Span は必ず原文 offset に対応させる。
- 単一改行だけを自動的な段落境界にはしない。表示上の折返しと論理段落を混同しないためである。
- 空行が一つもない入力は、入力全体を一つの Paragraph とする。

### 3.2 Sentence membership

既存 `MeaningGraph.clauses` の `source_span` を Paragraph Span と照合し、Clause / Proposition / PredicateFrame を所属 Paragraph へ集約する。

Paragraph 境界を跨ぐ Clause が発生した場合は自動修復せず `unresolved` に `paragraph_boundary_overlap` を記録する。

## 4. Data model

`ReadingAnalysis` の下へ次の構造を追加する設計とする。

### ParagraphStructure

- `paragraphs: list[ParagraphFrame]`
- `relations: list[ParagraphRelation]`
- `unresolved: list[dict]`
- `status: ItemStatus`

### ParagraphFrame

- `paragraph_id`
- `source_span: OriginalSpan`
- `clause_ids: list[str]`
- `proposition_ids: list[str]`
- `sentence_spans: list[OriginalSpan]`
- `topic_sentence_span: OriginalSpan | None`
- `topic_sentence_status: ItemStatus`
- `supporting_sentence_spans: list[OriginalSpan]`
- `central_theme_candidates: list[str]`
- `central_theme_evidence_ids: list[str]`
- `role: str` — `introduction / claim / support / example / problem / cause / solution / counterargument / qualification / conclusion / unknown` を初期候補とする。
- `status: ItemStatus`

### ParagraphRelation

- `relation_id`
- `source_paragraph_id`
- `target_paragraph_id`
- `relation`
- `marker: str | None`
- `evidence_span: OriginalSpan | None`
- `confidence`
- `status: ItemStatus`

Relation vocabulary は既存 `DiscourseRelation` と整合させ、初期段階では少なくとも以下を表現する。

- 並列・追加: `adds`
- 対比: `contrasts_with`
- 因果: `causes`
- 具体例: `exemplifies`
- 根拠: `justifies`
- 結論: `concludes`

## 5. Topic sentence extraction

中心文は「必ず第一文」と固定しない。ただし Evidence がない単一段落の最小Caseでは、第一文を deterministic fallback candidate として扱えるようにする。

優先する Evidence は次の順序で設計する。

1. 結論・主張を示す明示 Discourse Marker と既存 `DiscourseRelation`。
2. Paragraph 内 Proposition の主張性と、他文から `justifies / exemplifies / adds` で支持される関係。
3. `例えば / 具体的には` 等で始まる Example 文は Topic Candidate の優先度を下げる。
4. 上記 Evidence がなく、一段落内で候補を一意に決められない最小Caseでは第一文を fallback とし、その根拠種別を `position_fallback` として保持する。
5. 複数候補が同点で決着しない場合は推測で一つへ潰さず `AMBIGUOUS` とする。

最初の RED Test は Step 4 の単純Caseだけを固定する。高度な中心文判定は後続Testで段階的に追加する。

## 6. Paragraph role / R-14 categories

R-14 の分類を Paragraph と Sentence Evidence の両方で保持する。

- 一般論 → `claim` または `support` として Evidence を保持。
- 具体例 → `example`、関係は `exemplifies`。
- 問題 → `problem`。
- 原因 → `cause`、対象 Paragraph との Relation は `causes`。
- 対策 → `solution`。
- 反論 → `counterargument`、通常は `contrasts_with` Evidence を伴う。
- 限定 → `qualification`。

Marker だけで最終役割を断定せず、既存 Proposition / Scope / Discourse Evidence と一致しない場合は `AMBIGUOUS` を残す。

## 7. Extension points

### Sentence → Paragraph

`src/deterministic_japanese_parser_mcp/reading_runtime.py`

`DeterministicReadingRuntime.enrich()` は `graph.clauses`、`original_text`、Predicate / Proposition / Scope / Discourse を一か所で扱っている。Paragraph Span を作り、Clause / Proposition を集約する処理は **既存 `discourse = _discourse_relations(clauses)` の後、最終 `ReadingAnalysis(...)` を構築する前**に置く。

### Model storage

`src/deterministic_japanese_parser_mcp/models.py`

既存 `ReadingAnalysis` が Predicate / Scope / Attribution / Discourse を所有しているため、Paragraph Structure もここへ追加する。`MeaningGraph` 直下に別の Paragraph 正本を作らない。

### Engine integration

`src/deterministic_japanese_parser_mcp/engine.py`

既存 `reading_analysis` phase が `original_text` と Token を `DeterministicReadingRuntime.enrich()` へ渡している。Phase 3 初期実装では Engine に新しい独立Phaseを増やさず、この Reading Runtime 内で集約する。これにより既存 latency accounting と一度だけの Semantic Hash 確定を維持する。

### Paragraph → Document

R-15 は今回実装しない。後続 Document Reading は `ParagraphStructure.paragraphs` と `relations` を入力として集約できる境界だけを確保し、Paragraph 実装から文章全体要旨を先取りしない。

## 8. First RED test contract

入力:

`これは第一文。これは第二文。これが最終文。`

期待:

- Paragraph は1件。
- Paragraph Span は入力全体を指す。
- Sentence は3件。
- 最小Caseの Topic Sentence は第一文 `これは第一文。`。

現時点の Runtime / Model には Paragraph Structure が存在しないため、このTestは **意図的にRED** である。Runtime実装は次のChange Unitで行う。
