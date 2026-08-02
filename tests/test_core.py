from deterministic_japanese_parser_mcp import ParserEngine,AnalyzeRequest
def test_preserve_modify():
 r=ParserEngine().analyze(AnalyzeRequest(original_text="今のUIは殺すな。APIだけ変更しろ。"))
 assert {x.type for x in r.intents}>={"preserve","modify"}
def test_metaphor():
 r=ParserEngine().analyze(AnalyzeRequest(original_text="障害の火消しをして穴を塞げ。"))
 assert {x.expression for x in r.metaphors}>={"火消し","穴を塞ぐ"}
def test_original_span():
 t="ＡＰＩを変更しろ。";r=ParserEngine().analyze(AnalyzeRequest(original_text=t))
 assert r.intents and r.intents[0].span.source_text in t


def test_preserve_becomes_constraint_task_without_generic_request():
    response=ParserEngine().analyze(AnalyzeRequest(original_text="UIは残せ。APIだけ変更しろ。"))
    assert [task.intent_type for task in response.tasks] == ["preserve", "modify"]
