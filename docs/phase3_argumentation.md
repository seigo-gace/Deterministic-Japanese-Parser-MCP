# Phase 3-3 — 論証構造（R-16）

Status: **DESIGN / RED PREPARATION**

この文書は、02正本 R-16 に基づき、文章中の論証を非AI・非生成・決定論的に構造化する Phase 3-3 の実装準備設計である。このChange UnitではRuntime Codeを実装しない。

## 1. Canonical basis

R-16の要求は、論証を **主張・根拠・理由付け・明示前提・暗黙前提・反証／反論・限定** へ分解し、暗黙前提を事実として自動確定せず、Evidence付きCandidateとして保持することである。

Phase 3-3ではこの要求を満たすため、既存の `ParagraphStructure`、`SummaryResult` と、Reading Analysis内の明示Evidenceを利用する。生成AI、LLM、外部API、自由な補完推論は使用しない。

## 2. Purpose

文章全体について、少なくとも次の関係を追跡可能にする。

`主張 → 理由 → 根拠`

加えて、R-16で要求される明示前提、暗黙前提Candidate、反証／反論、限定を同じArgumentation Graph内で区別する。

## 3. Input

主要入力:

- `ParagraphStructure | None`
- `SummaryResult | None`

既存Evidenceとして参照可能な情報:

- `ReadingAnalysis.discourse_relations`
- `ReadingAnalysis.predicate_frames`
- `ReadingAnalysis.scope_operators`
- `ReadingAnalysis.attribution_frames`
- `ParagraphFrame.topic_sentence`
- Original Span / Clause ID / Paragraph ID

`ParagraphStructure` または `SummaryResult` が曖昧で、論証の主張候補を一意に確定できない場合は、Phase 3-3側で文章を補って確定しない。

## 4. Proposed output contract

将来のRuntime実装では、既存Pydantic Model規約に合わせて `ArgumentationResult` 相当を追加する。

想定要素:

- `claims`: 主張候補
- `reasons`: 主張を支える理由
- `evidence`: 例示・引用・出典・明示根拠
- `explicit_premises`: 本文に明示された前提
- `implicit_premise_candidates`: 本文に明示されていないが、論証Edgeに不足する前提候補。**事実確定しない**
- `counterarguments`: 反証・反対主張
- `rebuttals`: 反論への応答
- `limitations`: ただし・限定・例外等
- `edges`: 各要素間の支持／反対／限定関係
- `status`: `DETERMINED | AMBIGUOUS`
- `confidence`: 0.0〜1.0
- `unresolved`: 未確定理由とEvidence参照

各Unit / Edgeは可能な限り `clause_id`、`paragraph_id`、Original Span、利用した `discourse_relation_id` 等を保持し、原文へ追跡可能にする。

## 5. Deterministic extraction rules

### 5.1 Claim candidate

1. `SummaryResult.status == "DETERMINED"` の場合、`summary_text` と対応段落を文章全体の主張候補として最優先する。
2. SummaryがAMBIGUOUSの場合、候補を保持しても単一主張へ自動確定しない。
3. `ParagraphFrame.topic_sentence` は補助的Claim Candidateとして扱う。
4. 新しい主張文を生成しない。

### 5.2 Reason / evidence mapping

既存の明示談話MarkerをEvidenceとして使用する。現行Runtimeには `justifies`、`concludes`、`causes`、`exemplifies`、`contrasts_with`、`rephrases`、`adds` が存在する。

初期実装では次の固定Mappingを候補とする。

- `justifies`: 理由Candidate
- `concludes`: 結論／主張Candidate
- `causes`: 原因→結果の支持関係Candidate
- `exemplifies`: 具体例／Evidence Candidate
- `contrasts_with`: 反証・反論・限定Candidate
- `rephrases`: 同一主張の言換えCandidate。独立根拠へ昇格しない
- `adds`: 補足Candidate。単独で支持関係へ確定しない

Markerがない隣接文だけを理由・根拠と断定しない。

### 5.3 Explicit premise

条件・前提を示す既存Scope Evidenceが本文に明示され、対象Claim/Reasonとの作用関係が追跡できる場合だけ `explicit_premise` とする。

### 5.4 Implicit premise candidate

暗黙前提を自由生成しない。

明示されたClaimとReasonの間に論理的なWarrantが必要だが、本文内に対応文が存在しない場合は、次だけを記録できる。

- `candidate_type = "implicit_premise"`
- `text = None`
- `status = "AMBIGUOUS"`
- 関連するClaim / Reason ID
- 不足理由 (`warrant_not_explicit` 等)
- Evidence参照

つまり「暗黙前提が必要な可能性」は構造化してよいが、その内容を事実として捏造しない。

### 5.5 Counterargument / rebuttal / limitation

`contrasts_with`、否定・譲歩・限定Scope、明示的な「しかし／ただし／一方」等をEvidenceとし、対象Claimとの関係が追跡できる場合だけCandidate化する。

反対表現が存在しても、対象Claimが不明なら `unresolved` へ保持して関係を推測しない。

## 6. Decision / ambiguity policy

`DETERMINED` として論証関係を確定するには、最低限以下が必要。

1. Claim Candidateが明示Evidenceで特定できる。
2. Reason / Evidence / Counterargument等のEdgeに対応する本文Evidenceがある。
3. EdgeのSource / Targetが一意である。

以下の場合は `AMBIGUOUS` とする。

- Summary / Paragraph Structure自体が曖昧。
- Claim Candidateが複数で一意に選べない。
- Markerはあるが作用対象が特定できない。
- 理由と根拠の方向を本文Evidenceから決められない。
- 暗黙前提の内容を本文外から補う必要がある。

## 7. Confidence

Confidenceは明示Evidenceの種類とEdgeの一意性だけから決定論的に算出する。具体式はRuntime実装Change Unitで固定し、乱数・時刻・外部通信・AI出力を使用しない。

初期方針:

- 明示Marker + Source/Target一意: high confidence candidate
- Markerあり + Target不明: ambiguous / lower confidence
- Markerなしの推測関係: 確定しない
- implicit premise candidate: DETERMINED扱いにしない

## 8. Future integration points

Runtime実装を開始する場合の拡張点は以下とする。

- `src/deterministic_japanese_parser_mcp/models.py`
  - `ArgumentationResult` と必要なUnit / Edge Modelを追加
  - `ReadingAnalysis.argumentation` を追加
- `src/deterministic_japanese_parser_mcp/reading_runtime.py`
  - `_extract_argumentation()` を追加
  - `ParagraphStructure` / `SummaryResult` と既存Reading Evidenceから呼び出す

**この準備Change Unitでは上記Source Fileを変更しない。**

## 9. RED test skeleton

`tests/test_argumentation.py` に次の4 Contractを準備する。

- `test_argumentation_claim_reason_evidence`
- `test_argumentation_counterargument_and_limitation`
- `test_argumentation_implicit_premise_is_candidate_only`
- `test_argumentation_ambiguous_without_evidence`

Phase 3-2で発生した「意図的な `pytest.fail()` により通常CI全体を赤くする」状態は再発させない。この準備では4件を `xfail(strict=True)` の未実装Contractとして置き、Runtime実装Change Unitで実Assertionへ変えてGREEN化する。

## 10. Non-goals / boundaries

- Phase 3-3 Runtime実装を行わない。
- AI / LLM / OpenAI APIを使用しない。
- 暗黙前提の本文を生成しない。
- R-17具体／抽象対応以降を先行実装しない。
- Dictionary Pipeline / Ledger / needs-evidenceを変更しない。
- PR #27をMerge / Ready化しない。
- main / masterへPushしない。
