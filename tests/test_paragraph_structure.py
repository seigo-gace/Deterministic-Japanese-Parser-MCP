from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine


def test_single_paragraph_extraction():
    text = "これは第一文。これは第二文。これが最終文。"
    response = ParserEngine().analyze(AnalyzeRequest(original_text=text))
    paragraph_structure = response.meaning_graph.reading_analysis.paragraph_structure

    assert paragraph_structure is not None
    assert paragraph_structure.ambiguity_flag is True
    assert paragraph_structure.paragraphs == []

    text = "第一段落の第一文。第一段落の第二文。\n\n第二段落の第一文。"
    response = ParserEngine().analyze(AnalyzeRequest(original_text=text))
    paragraph_structure = response.meaning_graph.reading_analysis.paragraph_structure

    assert paragraph_structure is not None
    assert paragraph_structure.ambiguity_flag is False
    assert len(paragraph_structure.paragraphs) == 2

    first, second = paragraph_structure.paragraphs
    assert first.text == "第一段落の第一文。第一段落の第二文。"
    assert first.source_span.source_text == first.text
    assert len(first.sentence_spans) == 2
    assert first.topic_sentence == "第一段落の第一文。"
    assert first.topic_sentence_span is not None
    assert first.topic_sentence_span.source_text == first.topic_sentence

    assert second.text == "第二段落の第一文。"
    assert second.source_span.source_text == second.text
    assert len(second.sentence_spans) == 1
    assert second.topic_sentence == "第二段落の第一文。"
    assert second.topic_sentence_span is not None
    assert second.topic_sentence_span.source_text == second.topic_sentence
