from deterministic_japanese_parser_mcp import ParserEngine,AnalyzeRequest
def test_external_action_blocks_unknown():
 r=ParserEngine().analyze(AnalyzeRequest(original_text="謎の処理をほげろ。",execution_mode="external_action")); assert not r.execution_allowed
def test_reference_is_not_silently_selected():
 r=ParserEngine().analyze(AnalyzeRequest(original_text="これを比較しろ。",conversation_context=["案A","案B"])); assert r.references and r.references[0].selected is None
def test_contradiction_blocks_external_action():
 r=ParserEngine().analyze(AnalyzeRequest(original_text="実装しろ。実装するな。",execution_mode="external_action")); assert r.contradictions and not r.execution_allowed
