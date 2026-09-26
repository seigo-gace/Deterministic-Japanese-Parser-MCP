from deterministic_japanese_parser_mcp import ParserEngine,AnalyzeRequest
from deterministic_japanese_parser_mcp.graph_guard import GraphGuard
from deterministic_japanese_parser_mcp.models import MeaningGraph, OriginalSpan, Proposition
def test_external_action_blocks_unknown():
 r=ParserEngine().analyze(AnalyzeRequest(original_text="謎の処理をほげろ。",execution_mode="external_action"))
 assert not r.execution_allowed
def test_reference_is_not_silently_selected():
 r=ParserEngine().analyze(AnalyzeRequest(original_text="これを比較しろ。",conversation_context=["案A","案B"]))
 assert r.references and r.references[0].selected is None

def test_contradiction_blocks_external_action():
    r=ParserEngine().analyze(AnalyzeRequest(original_text="実装しろ。実装するな。",execution_mode="external_action"))
    assert r.contradictions
    assert not r.execution_allowed


def test_action_relevant_lexical_ambiguity_has_specific_block_reason():
    graph = MeaningGraph(
        propositions=[Proposition(
            proposition_id="P-001",
            predicate="実行する",
            intent_type="action",
            value="実行",
            executable_candidate=True,
            source_span=OriginalSpan(start=0, end=2, source_text="実行"),
        )],
        unresolved=[{
            "type": "lexical_action_ambiguity",
            "status": "AMBIGUOUS",
            "related_proposition_ids": ["P-001"],
        }],
    )

    allowed, blocked, _closure = GraphGuard().evaluate(
        graph,
        contradictions=[],
        unsupported=[],
        timeouts=[],
        external_action=True,
    )

    assert not allowed
    assert blocked == ["AMBIGUOUS_ACTION_LEXEME"]
