from scripts.sync_project_control_readme import (
    JA_BLOCK,
    synchronize_japanese,
)


def test_project_control_sync_is_idempotent_at_eof_without_newline() -> None:
    text = f"# README\n\n{JA_BLOCK}"
    assert synchronize_japanese(text) == text


def test_project_control_sync_is_idempotent_at_eof_with_newline() -> None:
    text = f"# README\n\n{JA_BLOCK}\n"
    assert synchronize_japanese(text) == text


def test_project_control_sync_keeps_one_blank_line_before_following_content() -> None:
    text = f"# README\n\n{JA_BLOCK}\n\n\n## Next\n"
    expected = f"# README\n\n{JA_BLOCK}\n\n## Next\n"
    assert synchronize_japanese(text) == expected
