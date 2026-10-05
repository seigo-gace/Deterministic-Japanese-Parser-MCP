from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine
from deterministic_japanese_parser_mcp.normalizer import normalize_with_map


ASTERA_LONG_INPUT = (
    "社内の業務ファイル保存方式について候補Aと候補Bの判断材料を作成する。"
    "Astera自身は最終判断をしない。"
    "人間またはAIが判断できるよう確認できた事実だけを整理する。"
    "根拠を確認できない項目は根拠なしまたは確認できずと明示する。"
    "推測で穴埋めしない。"
)


def test_plain_form_action_requests_are_intent_candidates() -> None:
    engine = ParserEngine()
    normalized, mapping = normalize_with_map(ASTERA_LONG_INPUT)

    intents, timeouts = engine.rules.extract(
        normalized,
        mapping,
        ASTERA_LONG_INPUT,
    )

    assert not timeouts
    requests = [item for item in intents if item.type == "request"]
    assert [item.rule_id for item in requests] == [
        "REQUEST-009",
        "REQUEST-009",
        "REQUEST-009",
    ]
    assert [item.span.source_text for item in requests] == [
        "社内の業務ファイル保存方式について候補Aと候補Bの判断材料を作成する",
        "人間またはAIが判断できるよう確認できた事実だけを整理する",
        "根拠を確認できない項目は根拠なしまたは確認できずと明示する",
    ]


def test_astara_long_input_keeps_plain_form_requests_executable() -> None:
    response = ParserEngine().analyze(
        AnalyzeRequest(original_text=ASTERA_LONG_INPUT)
    )

    requested = [
        item
        for item in response.meaning_graph.propositions
        if item.predicate in {"作成する", "整理する", "明示する"}
    ]

    assert [item.intent_type for item in requested] == [
        "request",
        "request",
        "request",
    ]
    assert all(item.executable_candidate for item in requested)
    assert [item.predicate for item in requested] == [
        "作成する",
        "整理する",
        "明示する",
    ]
    assert len(response.task_graph.tasks) == 3
    assert [item.proposition_id for item in response.task_graph.tasks] == [
        item.proposition_id for item in requested
    ]
