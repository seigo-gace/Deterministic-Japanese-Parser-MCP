from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.check_contribution_rights import (  # noqa: E402
    RightsDecision,
    commit_has_valid_signoff,
    find_owner_rights_decision,
    unsigned_commit_shas,
    validate_contribution_rights,
)


def _commit(sha: str, message: str) -> dict:
    return {"sha": sha, "commit": {"message": message}}


def _review(
    *,
    reviewer: str = "seigo-gace",
    state: str = "APPROVED",
    commit_id: str = "head-sha",
    body: str,
    review_id: int = 1,
) -> dict:
    return {
        "id": review_id,
        "user": {"login": reviewer},
        "state": state,
        "commit_id": commit_id,
        "body": body,
    }


def test_dco_accepts_valid_signoff() -> None:
    assert commit_has_valid_signoff(
        "fix: preserve scope\n\nSigned-off-by: Example Contributor <dev@example.com>"
    )


def test_dco_rejects_missing_or_malformed_signoff() -> None:
    assert not commit_has_valid_signoff("fix: preserve scope")
    assert not commit_has_valid_signoff("Signed-off-by: Example Contributor")
    assert not commit_has_valid_signoff("Signed-off-by: Bot <not-an-email>")


def test_unsigned_commit_list_preserves_short_sha() -> None:
    commits = [
        _commit("a" * 40, "Signed-off-by: A Person <a@example.com>"),
        _commit("b" * 40, "missing signoff"),
    ]
    assert unsigned_commit_shas(commits) == ["b" * 12]


def test_owner_pull_request_is_exempt_from_inbound_gate() -> None:
    decision = validate_contribution_rights(
        author="seigo-gace",
        owner="seigo-gace",
        head_sha="head-sha",
        commits=[],
        reviews=[],
    )
    assert decision == RightsDecision(status="owner", review_id=None)


def test_external_contribution_requires_all_commits_signed() -> None:
    with pytest.raises(ValueError, match="Missing valid DCO"):
        validate_contribution_rights(
            author="external-user",
            owner="seigo-gace",
            head_sha="head-sha",
            commits=[_commit("c" * 40, "missing signoff")],
            reviews=[],
        )


def test_current_head_owner_approval_accepts_cla_record() -> None:
    reviews = [
        _review(
            body=(
                "CLA-Status: accepted\n"
                "CLA-Version: 1.0 — 2026-08-05\n"
                "CLA-Record: sha256:1234"
            ),
            review_id=12,
        )
    ]
    decision = find_owner_rights_decision(
        reviews, owner="seigo-gace", head_sha="head-sha"
    )
    assert decision == RightsDecision(status="accepted", review_id=12)


def test_stale_or_non_owner_review_does_not_authorize_merge() -> None:
    body = (
        "CLA-Status: accepted\n"
        "CLA-Version: 1.0\n"
        "CLA-Record: sha256:1234"
    )
    reviews = [
        _review(body=body, commit_id="old-sha"),
        _review(body=body, reviewer="another-maintainer"),
    ]
    assert (
        find_owner_rights_decision(
            reviews, owner="seigo-gace", head_sha="head-sha"
        )
        is None
    )


def test_cla_acceptance_requires_version_and_private_record() -> None:
    reviews = [
        _review(body="CLA-Status: accepted\nCLA-Version: 1.0"),
        _review(body="CLA-Status: accepted\nCLA-Record: sha256:1234"),
    ]
    assert (
        find_owner_rights_decision(
            reviews, owner="seigo-gace", head_sha="head-sha"
        )
        is None
    )


def test_cla_exemption_requires_written_reason() -> None:
    invalid = [_review(body="CLA-Status: exempt")]
    valid = [
        _review(
            body="CLA-Status: exempt\nCLA-Reason: obvious typo only",
            review_id=8,
        )
    ]
    assert (
        find_owner_rights_decision(
            invalid, owner="seigo-gace", head_sha="head-sha"
        )
        is None
    )
    assert find_owner_rights_decision(
        valid, owner="seigo-gace", head_sha="head-sha"
    ) == RightsDecision(status="exempt", review_id=8)


def test_external_contribution_passes_with_dco_and_owner_record() -> None:
    commits = [
        _commit(
            "d" * 40,
            "feat: add reviewed rule\n\n"
            "Signed-off-by: Example Contributor <dev@example.com>",
        )
    ]
    reviews = [
        _review(
            body=(
                "CLA-Status: accepted\n"
                "CLA-Version: 1.0 — 2026-08-05\n"
                "CLA-Record: sha256:abcd"
            )
        )
    ]
    assert validate_contribution_rights(
        author="external-user",
        owner="seigo-gace",
        head_sha="head-sha",
        commits=commits,
        reviews=reviews,
    ).status == "accepted"
