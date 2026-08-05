from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

SIGNOFF_RE = re.compile(
    r"(?im)^Signed-off-by:\s+.+?\s+<[^<>\s]+@[^<>\s]+>\s*$"
)
CLA_STATUS_RE = re.compile(r"(?im)^CLA-Status:\s*(accepted|exempt)\s*$")
CLA_VERSION_RE = re.compile(r"(?im)^CLA-Version:\s*\S.+$")
CLA_RECORD_RE = re.compile(r"(?im)^CLA-Record:\s*\S.+$")
CLA_REASON_RE = re.compile(r"(?im)^CLA-Reason:\s*\S.+$")


@dataclass(frozen=True)
class RightsDecision:
    status: str
    review_id: int | None


def commit_has_valid_signoff(message: str) -> bool:
    return bool(SIGNOFF_RE.search(message))


def unsigned_commit_shas(commits: Iterable[Mapping[str, Any]]) -> list[str]:
    unsigned: list[str] = []
    for item in commits:
        sha = str(item.get("sha", ""))
        commit = item.get("commit", {})
        message = str(commit.get("message", "")) if isinstance(commit, Mapping) else ""
        if not commit_has_valid_signoff(message):
            unsigned.append(sha[:12] or "unknown")
    return unsigned


def _review_body(review: Mapping[str, Any]) -> str:
    body = review.get("body")
    return str(body) if body is not None else ""


def find_owner_rights_decision(
    reviews: Iterable[Mapping[str, Any]],
    *,
    owner: str,
    head_sha: str,
) -> RightsDecision | None:
    accepted: RightsDecision | None = None
    exempt: RightsDecision | None = None

    for review in reviews:
        user = review.get("user", {})
        reviewer = str(user.get("login", "")) if isinstance(user, Mapping) else ""
        state = str(review.get("state", "")).upper()
        commit_id = str(review.get("commit_id", ""))
        body = _review_body(review)

        if reviewer.casefold() != owner.casefold():
            continue
        if state != "APPROVED" or commit_id != head_sha:
            continue

        status_match = CLA_STATUS_RE.search(body)
        if not status_match:
            continue

        review_id_value = review.get("id")
        review_id = review_id_value if isinstance(review_id_value, int) else None
        status = status_match.group(1).casefold()

        if status == "accepted":
            if CLA_VERSION_RE.search(body) and CLA_RECORD_RE.search(body):
                accepted = RightsDecision(status="accepted", review_id=review_id)
        elif status == "exempt":
            if CLA_REASON_RE.search(body):
                exempt = RightsDecision(status="exempt", review_id=review_id)

    return accepted or exempt


def github_get_all(
    api_root: str,
    path: str,
    *,
    token: str,
    timeout_seconds: int = 30,
) -> list[dict[str, Any]]:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "djpmcp-contribution-rights",
    }
    items: list[dict[str, Any]] = []
    page = 1

    while True:
        separator = "&" if "?" in path else "?"
        url = f"{api_root}{path}{separator}per_page=100&page={page}"
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GitHub API failed: {exc.code} {detail}") from exc

        if not isinstance(payload, list):
            raise RuntimeError(f"Expected list response from {url}")
        items.extend(item for item in payload if isinstance(item, dict))
        if len(payload) < 100:
            return items
        page += 1


def validate_contribution_rights(
    *,
    author: str,
    owner: str,
    head_sha: str,
    commits: Iterable[Mapping[str, Any]],
    reviews: Iterable[Mapping[str, Any]],
) -> RightsDecision:
    if author.casefold() == owner.casefold():
        return RightsDecision(status="owner", review_id=None)

    commit_list = list(commits)
    unsigned = unsigned_commit_shas(commit_list)
    if unsigned:
        raise ValueError(
            "Missing valid DCO Signed-off-by line: " + ", ".join(unsigned)
        )

    decision = find_owner_rights_decision(reviews, owner=owner, head_sha=head_sha)
    if decision is None:
        raise ValueError(
            "No current-head APPROVED review from the Project Owner contains "
            "a valid CLA accepted or exempt record."
        )
    return decision


def main() -> int:
    token = os.environ["GH_TOKEN"]
    repository = os.environ["GH_REPOSITORY"]
    owner = os.environ["GH_PROJECT_OWNER"]
    pr_number = os.environ["PR_NUMBER"]
    author = os.environ["PR_AUTHOR"]
    head_sha = os.environ["PR_HEAD_SHA"]

    if author.casefold() == owner.casefold():
        print("Project Owner pull request: inbound DCO/CLA gate is not required.")
        return 0

    api_root = f"https://api.github.com/repos/{repository}"
    commits = github_get_all(api_root, f"/pulls/{pr_number}/commits", token=token)
    reviews = github_get_all(api_root, f"/pulls/{pr_number}/reviews", token=token)

    try:
        decision = validate_contribution_rights(
            author=author,
            owner=owner,
            head_sha=head_sha,
            commits=commits,
            reviews=reviews,
        )
    except ValueError as exc:
        print(str(exc))
        print("Each external commit must contain:")
        print("Signed-off-by: Real Name <email@example.com>")
        print("A current-head Project Owner APPROVED review must contain either:")
        print("CLA-Status: accepted")
        print("CLA-Version: <version>")
        print("CLA-Record: <private record identifier or digest>")
        print("Or:")
        print("CLA-Status: exempt")
        print("CLA-Reason: <non-substantive contribution reason>")
        return 1

    print(
        f"Contribution rights verified: commits={len(commits)} "
        f"dco=pass cla={decision.status} head={head_sha}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
