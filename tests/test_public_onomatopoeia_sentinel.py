from __future__ import annotations

from tools.public_onomatopoeia_sources import _resolved_local_meaning


def test_verified_j_ono_refer_sentinel_is_not_semantic_meaning() -> None:
    meaning, status = _resolved_local_meaning(
        {"meaning": "s", "refer": "biri:1", "type": ""}
    )
    assert meaning == ""
    assert status == "upstream-undocumented-sentinel"


def test_plain_s_without_refer_is_not_silently_removed() -> None:
    meaning, status = _resolved_local_meaning(
        {"meaning": "s", "refer": "", "type": ""}
    )
    assert meaning == "s"
    assert status == "source-authored"


def test_typed_s_with_refer_is_not_silently_removed() -> None:
    meaning, status = _resolved_local_meaning(
        {"meaning": "s", "refer": "biri:1", "type": "s"}
    )
    assert meaning == "s"
    assert status == "source-authored"
