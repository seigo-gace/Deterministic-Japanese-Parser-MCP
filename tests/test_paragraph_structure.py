from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine


def test_single_paragraph_extraction():
    text = "これは第一文。これは第二文。これが最終文。"
    response = ParserEngine().analyze(AnalyzeRequest(original_text=text))
    reading = response.meaning_graph.reading_analysis

    paragraphs = reading.paragraph_structure.paragraphs
    assert len(paragraphs) == 1
    paragraph = paragraphs[0]
    assert paragraph.source_span.source_text == text
    assert len(paragraph.sentence_spans) == 3
    assert paragraph.topic_sentence_span.source_text == "これは第一文。"
