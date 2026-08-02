from pathlib import Path

from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine
from deterministic_japanese_parser_mcp.config import Settings
from deterministic_japanese_parser_mcp.logger import mask_sensitive_text


def test_kara_is_not_question_particle():
    response = ParserEngine().analyze(AnalyzeRequest(original_text="落ち着いてから穴を塞げ。"))
    assert "question" not in {intent.type for intent in response.intents}


def test_canonical_incident_tasks_are_ordered():
    response = ParserEngine().analyze(
        AnalyzeRequest(
            original_text="障害の火消しをして、落ち着いてから穴を全部塞げ。最後にGitHubへ入れろ。"
        )
    )
    assert [task.target for task in response.tasks] == ["火消し", "落ち着く", "穴を塞ぐ", "最後にGitHubへ"]
    assert [task.execution_order for task in response.tasks] == [1, 2, 3, 4]


def test_protected_element_blocks_external_change():
    response = ParserEngine().analyze(
        AnalyzeRequest(
            original_text="UIを変更しろ。",
            protected_elements=["UI"],
            execution_mode="external_action",
        )
    )
    assert not response.execution_allowed
    assert any(item["type"] == "protected_element_conflict" for item in response.contradictions)


def test_reference_candidates_respect_limit(tmp_path: Path):
    settings = Settings(max_candidates=2, log_path=tmp_path / "parser.jsonl")
    response = ParserEngine(settings).analyze(
        AnalyzeRequest(
            original_text="これを比較しろ。",
            conversation_context=["案1", "案2", "案3", "案4"],
        )
    )
    assert len(response.references[0].candidates) == 2


def test_sensitive_log_masking():
    masked = mask_sensitive_text(
        "mail=user@example.com token=abcdefghijklmnop 4111111111111111 Bearer abcdefghijklmnop"
    )
    assert "user@example.com" not in masked
    assert "abcdefghijklmnop" not in masked
    assert "4111111111111111" not in masked
    assert "<EMAIL>" in masked
    assert "<SECRET>" in masked
    assert "<LONG_NUMBER>" in masked
