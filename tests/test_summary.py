from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine
from deterministic_japanese_parser_mcp.models import (
    OriginalSpan,
    ParagraphFrame,
    ParagraphStructure,
)
from deterministic_japanese_parser_mcp.reading_runtime import (
    DeterministicReadingRuntime,
)


def test_single_paragraph_summary():
    """明示的な単一ParagraphStructureから要旨を抽出できること。"""
    text = "今日は良い天気だ。公園に行こう。"
    span = OriginalSpan(start=0, end=len(text), source_text=text)
    structure = ParagraphStructure(
        paragraphs=[
            ParagraphFrame(
                paragraph_id="PG-001",
                text=text,
                start_char=0,
                end_char=len(text),
                source_span=span,
                sentence_spans=[span],
                topic_sentence="今日は良い天気だ。",
                topic_sentence_start=0,
                topic_sentence_end=len("今日は良い天気だ。"),
                topic_sentence_span=OriginalSpan(
                    start=0,
                    end=len("今日は良い天気だ。"),
                    source_text="今日は良い天気だ。",
                ),
            )
        ],
        ambiguity_flag=False,
    )

    summary = DeterministicReadingRuntime()._extract_summary(structure)

    assert summary.status == "DETERMINED"
    assert summary.summary_text == "今日は良い天気だ。"
    assert summary.source_paragraph_indices == [0]


def test_multi_paragraph_summary():
    """複数の明示段落から文章全体の要旨を抽出できること。"""
    text = "第一段落の主張。\n\n第二段落の詳細。\n\n第三段落の結論。"
    response = ParserEngine().analyze(AnalyzeRequest(original_text=text))
    summary = response.meaning_graph.reading_analysis.summary

    assert summary is not None
    assert summary.status == "DETERMINED"
    assert summary.summary_text == "第一段落の主張。"
    assert summary.source_paragraph_indices == [0]


def test_ambiguous_summary():
    """段落境界Evidenceがない入力は推測せずAMBIGUOUSを返すこと。"""
    text = "Aという意見がある。しかしBという意見もある。"
    response = ParserEngine().analyze(AnalyzeRequest(original_text=text))
    summary = response.meaning_graph.reading_analysis.summary

    assert summary is not None
    assert summary.status == "AMBIGUOUS"
    assert summary.summary_text is None
    assert summary.confidence == 0.0


def test_summary_confidence():
    """要旨confidenceが0.0〜1.0の範囲で決定論的に算出されること。"""
    text = "明確な主張。\n\n補足情報。\n\n結論。"
    first = ParserEngine().analyze(AnalyzeRequest(original_text=text))
    second = ParserEngine().analyze(AnalyzeRequest(original_text=text))
    first_summary = first.meaning_graph.reading_analysis.summary
    second_summary = second.meaning_graph.reading_analysis.summary

    assert first_summary is not None
    assert second_summary is not None
    assert 0.0 <= first_summary.confidence <= 1.0
    assert first_summary.confidence == second_summary.confidence
