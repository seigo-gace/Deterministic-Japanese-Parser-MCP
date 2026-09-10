from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine
from deterministic_japanese_parser_mcp.lexical_graph import LexicalGraphEnricher
from deterministic_japanese_parser_mcp.models import (
    ItemStatus,
    LexicalCandidate,
    MeaningGraph,
    OriginalSpan,
    Token,
)


def test_compiled_open_lexicon_is_emitted_as_meaning_graph_nodes():
    engine = ParserEngine()
    response = engine.analyze(
        AnalyzeRequest(
            original_text="日本を確認する。",
            deadline_ms=5000,
        )
    )

    assert response.meaning_graph.graph_version == "2.3.0"
    assert response.meaning_graph.semantic_hash
    nodes = response.meaning_graph.lexical_nodes
    assert nodes
    assert response.metrics["lexical_node_count"] == len(nodes)
    assert response.metrics["meaning_graph_lexical_node_count"] == len(nodes)
    assert response.meaning_graph.quality_annotations[
        "context_candidate_registry_used"
    ] is False

    japan = next(item for item in nodes if item.surface == "日本")
    assert japan.status == ItemStatus.RESOLVED
    assert japan.selected_record_id
    assert japan.related_proposition_ids
    assert japan.candidates[0].source_dataset == "JMdict"
    assert "surface_exact" in japan.candidate_evidence[
        japan.selected_record_id
    ]

    suru = next(item for item in nodes if item.surface == "する")
    assert suru.status == ItemStatus.RESOLVED
    assert suru.selected_record_id
    selected = next(
        item
        for item in suru.candidates
        if item.record_id == suru.selected_record_id
    )
    assert "する" in selected.readings
    assert "token_reading_match" in suru.candidate_evidence[
        suru.selected_record_id
    ]
    assert suru.resolution_reason == "deterministic_context_margin"

    assert response.meaning_graph.quality_annotations[
        "semantic_auto_promotion"
    ] is False
    assert response.meaning_graph.quality_annotations[
        "intent_auto_promotion"
    ] is False
    assert response.meaning_graph.quality_annotations[
        "task_auto_promotion"
    ] is False
    assert response.meaning_graph.quality_annotations[
        "external_action_auto_promotion"
    ] is False


def test_equal_lexical_candidates_remain_ambiguous_without_guessing():
    span = OriginalSpan(start=0, end=1, source_text="橋")
    token = Token(
        surface="橋",
        normalized="橋",
        reading=None,
        pos=["名詞"],
        span=span,
        lexical_candidates=[
            LexicalCandidate(
                record_id="JMD-A",
                lemma="橋",
                matched_text="橋",
                match_type="surface",
                part_of_speech=["noun (common) (futsuumeishi)"],
                source_dataset="JMdict",
                source_version="test",
                source_license="CC-BY-SA-4.0",
            ),
            LexicalCandidate(
                record_id="JMD-B",
                lemma="橋",
                matched_text="橋",
                match_type="surface",
                part_of_speech=["noun (common) (futsuumeishi)"],
                source_dataset="JMdict",
                source_version="test",
                source_license="CC-BY-SA-4.0",
            ),
        ],
        lexical_candidate_total=2,
        lexical_status="AMBIGUOUS",
    )

    graph = LexicalGraphEnricher().enrich(
        MeaningGraph(),
        tokens=[token],
        original_text="橋",
        conversation_context=[],
        known_entities=[],
    )

    assert len(graph.lexical_nodes) == 1
    assert graph.semantic_hash
    node = graph.lexical_nodes[0]
    assert node.status == ItemStatus.AMBIGUOUS
    assert node.selected_record_id is None
    assert node.resolution_reason == "insufficient_context_margin"
    assert graph.quality_annotations["ambiguous_lexical_nodes"] == 1
    assert graph.unresolved == []


def test_truncated_candidate_lists_cannot_be_resolved():
    span = OriginalSpan(start=0, end=2, source_text="対象")
    token = Token(
        surface="対象",
        normalized="対象",
        reading="タイショウ",
        pos=["名詞"],
        span=span,
        lexical_candidates=[
            LexicalCandidate(
                record_id="JMD-ONE",
                lemma="対象",
                matched_text="対象",
                match_type="surface",
                readings=["たいしょう"],
                part_of_speech=["noun (common) (futsuumeishi)"],
                source_dataset="JMdict",
                source_version="test",
                source_license="CC-BY-SA-4.0",
            )
        ],
        lexical_candidate_total=9,
        lexical_status="AMBIGUOUS",
    )

    graph = LexicalGraphEnricher().enrich(
        MeaningGraph(),
        tokens=[token],
        original_text="対象",
        conversation_context=[],
        known_entities=[],
    )

    node = graph.lexical_nodes[0]
    assert node.selected_record_id is None
    assert node.resolution_reason == "candidate_list_truncated"
    assert node.status == ItemStatus.AMBIGUOUS
