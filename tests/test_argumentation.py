from deterministic_japanese_parser_mcp.models import (
    AttributionFrame,
    Clause,
    DiscourseRelation,
    ItemStatus,
    OriginalSpan,
    ParagraphFrame,
    ParagraphStructure,
    ScopeOperator,
    SummaryResult,
)
from deterministic_japanese_parser_mcp.reading_runtime import (
    DeterministicReadingRuntime,
)


def _span(start: int, text: str) -> OriginalSpan:
    return OriginalSpan(start=start, end=start + len(text), source_text=text)


def _clause(clause_id: str, start: int, text: str) -> Clause:
    return Clause(
        clause_id=clause_id,
        text=text,
        source_span=_span(start, text),
    )


def _structure(clauses: list[Clause]) -> ParagraphStructure:
    start = min(item.source_span.start for item in clauses)
    end = max(item.source_span.end for item in clauses)
    paragraph = ParagraphFrame(
        paragraph_id="PG-001",
        text="".join(item.text for item in clauses),
        start_char=start,
        end_char=end,
        source_span=OriginalSpan(
            start=start,
            end=end,
            source_text="".join(item.text for item in clauses),
        ),
        clause_ids=[item.clause_id for item in clauses],
        sentence_spans=[item.source_span for item in clauses],
        topic_sentence=clauses[0].text,
        topic_sentence_start=clauses[0].source_span.start,
        topic_sentence_end=clauses[0].source_span.end,
        topic_sentence_span=clauses[0].source_span,
    )
    return ParagraphStructure(
        paragraphs=[paragraph],
        ambiguity_flag=False,
        status=ItemStatus.RESOLVED,
    )


def _summary(claim: Clause) -> SummaryResult:
    return SummaryResult(
        summary_text=claim.text,
        confidence=0.95,
        status="DETERMINED",
        candidates=[],
        source_paragraph_indices=[0],
    )


def test_argumentation_claim_reason_evidence():
    claim = _clause("C-001", 0, "この方式を採用すべきだ。")
    reason = _clause("C-002", 20, "なぜなら処理が安定するからだ。")
    example = _clause("C-003", 50, "例えば障害時にも復旧できる。")

    result = DeterministicReadingRuntime._extract_argumentation(
        paragraph_structure=_structure([claim, reason, example]),
        summary=_summary(claim),
        clauses=[claim, reason, example],
        discourse_relations=[
            DiscourseRelation(
                relation_id="DR-001",
                source_clause_id=claim.clause_id,
                target_clause_id=reason.clause_id,
                relation="justifies",
                marker="なぜなら",
                confidence=0.98,
            ),
            DiscourseRelation(
                relation_id="DR-002",
                source_clause_id=reason.clause_id,
                target_clause_id=example.clause_id,
                relation="exemplifies",
                marker="例えば",
                confidence=0.98,
            ),
        ],
        scope_operators=[],
        attribution_frames=[],
    )

    assert result.claims
    assert any(item.clause_id == reason.clause_id for item in result.reasons)
    assert any(item.clause_id == example.clause_id for item in result.evidence)
    assert any(
        edge.relation == "supports"
        and edge.source_component_id
        == next(item.component_id for item in result.reasons if item.clause_id == reason.clause_id)
        for edge in result.edges
    )
    assert any(
        "DISCOURSE:DR-001" in edge.evidence_ids
        for edge in result.edges
    )


def test_argumentation_counterargument_and_limitation():
    claim = _clause("C-001", 0, "この方式は有効だ。")
    counter = _clause("C-002", 20, "しかし初期費用は高い。")
    rebuttal = _clause("C-003", 45, "しかし長期運用では回収できる。")
    limitation = _clause("C-004", 80, "ただし小規模環境には向かない。")

    result = DeterministicReadingRuntime._extract_argumentation(
        paragraph_structure=_structure([claim, counter, rebuttal, limitation]),
        summary=_summary(claim),
        clauses=[claim, counter, rebuttal, limitation],
        discourse_relations=[
            DiscourseRelation(
                relation_id="DR-001",
                source_clause_id=claim.clause_id,
                target_clause_id=counter.clause_id,
                relation="contrasts_with",
                marker="しかし",
                confidence=0.98,
            ),
            DiscourseRelation(
                relation_id="DR-002",
                source_clause_id=counter.clause_id,
                target_clause_id=rebuttal.clause_id,
                relation="contrasts_with",
                marker="しかし",
                confidence=0.98,
            ),
            DiscourseRelation(
                relation_id="DR-003",
                source_clause_id=claim.clause_id,
                target_clause_id=limitation.clause_id,
                relation="contrasts_with",
                marker="ただし",
                confidence=0.98,
            ),
        ],
        scope_operators=[],
        attribution_frames=[],
    )

    assert [item.clause_id for item in result.counterarguments] == [counter.clause_id]
    assert [item.clause_id for item in result.rebuttals] == [rebuttal.clause_id]
    assert [item.clause_id for item in result.limitations] == [limitation.clause_id]
    assert any(edge.relation == "opposes" for edge in result.edges)
    assert any(edge.relation == "limits" for edge in result.edges)


def test_argumentation_implicit_premise_is_candidate_only():
    claim = _clause("C-001", 0, "この設計を採用すべきだ。")
    reason = _clause("C-002", 25, "なぜなら再現性が高いからだ。")

    result = DeterministicReadingRuntime._extract_argumentation(
        paragraph_structure=_structure([claim, reason]),
        summary=_summary(claim),
        clauses=[claim, reason],
        discourse_relations=[
            DiscourseRelation(
                relation_id="DR-001",
                source_clause_id=claim.clause_id,
                target_clause_id=reason.clause_id,
                relation="justifies",
                marker="なぜなら",
                confidence=0.98,
            )
        ],
        scope_operators=[],
        attribution_frames=[],
    )

    assert len(result.implicit_premise_candidates) == 1
    candidate = result.implicit_premise_candidates[0]
    assert candidate.text is None
    assert candidate.status == "AMBIGUOUS"
    assert len(candidate.related_component_ids) == 2
    assert any(
        item.get("reason") == "warrant_not_explicit"
        and item.get("component_id") == candidate.component_id
        for item in result.unresolved
    )
    assert result.status == "AMBIGUOUS"


def test_argumentation_ambiguous_without_evidence():
    result = DeterministicReadingRuntime._extract_argumentation(
        paragraph_structure=ParagraphStructure(
            paragraphs=[],
            ambiguity_flag=True,
            unresolved=[{
                "type": "paragraph_boundary_not_explicit",
                "status": ItemStatus.AMBIGUOUS.value,
            }],
            status=ItemStatus.AMBIGUOUS,
        ),
        summary=SummaryResult(
            status="AMBIGUOUS",
            candidates=[],
            confidence=0.0,
        ),
        clauses=[],
        discourse_relations=[],
        scope_operators=[],
        attribution_frames=[],
    )

    assert result.status == "AMBIGUOUS"
    assert result.confidence == 0.0
    assert result.claims == []
    assert result.edges == []
    assert any(
        item.get("type") == "argumentation_claim_not_determined"
        for item in result.unresolved
    )


def test_argumentation_explicit_premise_uses_scope_evidence():
    claim = _clause("C-001", 0, "条件を満たすなら採用する。")
    structure = _structure([claim])
    scope = ScopeOperator(
        operator_id="SO-001",
        clause_id=claim.clause_id,
        operator_type="condition",
        semantic_value="premise_condition",
        marker="なら",
        source_span=_span(5, "なら"),
        operand_spans=[claim.source_span],
        target_frame_ids=["PF-001"],
        status=ItemStatus.RESOLVED,
    )

    result = DeterministicReadingRuntime._extract_argumentation(
        paragraph_structure=structure,
        summary=_summary(claim),
        clauses=[claim],
        discourse_relations=[],
        scope_operators=[scope],
        attribution_frames=[
            AttributionFrame(
                attribution_id="AT-001",
                clause_id=claim.clause_id,
                attribution_type="hearsay",
                content_span=claim.source_span,
                source="仕様書",
                reporting_predicate="伝聞",
                status=ItemStatus.RESOLVED,
            )
        ],
    )

    assert len(result.explicit_premises) == 1
    premise = result.explicit_premises[0]
    assert premise.text == "なら"
    assert "SCOPE:SO-001" in premise.evidence_ids
    assert any(edge.relation == "conditions" for edge in result.edges)
