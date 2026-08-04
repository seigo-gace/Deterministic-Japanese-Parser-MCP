#!/usr/bin/env python3
"""Apply explicit review decisions to a dictionary proposal bundle."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dictionary_supply.proposals import load_bundle


def load_decisions(path: Path) -> dict[str, dict]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    decisions: dict[str, dict] = {}
    for item in value.get("decisions", []):
        proposal_id = item.get("proposal_id")
        if not proposal_id:
            raise ValueError("decision proposal_id is required")
        if proposal_id in decisions:
            raise ValueError(f"duplicate decision: {proposal_id}")
        status = item.get("status")
        if status not in {"approved", "rejected", "blocked"}:
            raise ValueError(f"invalid review status: {proposal_id}: {status}")
        notes = item.get("notes", [])
        if not notes:
            raise ValueError(f"review notes are required: {proposal_id}")
        decisions[proposal_id] = item
    return decisions


def validate_approval(proposal: dict, decision: dict) -> None:
    proposal_id = proposal["proposal_id"]
    if proposal.get("conflicts") and not decision.get("conflict_resolution"):
        raise ValueError(
            f"approved proposal requires conflict_resolution: {proposal_id}"
        )
    kind = proposal.get("kind")
    payload = proposal.get("payload", {})
    evidence = proposal.get("evidence", [])
    if not evidence or any(not item.get("license") for item in evidence):
        raise ValueError(f"source license evidence is required: {proposal_id}")
    if kind == "metaphor":
        for key in ("expression", "interpretation", "domain"):
            if not payload.get(key):
                raise ValueError(f"metaphor.{key} is required: {proposal_id}")
        if not decision.get("positive_examples"):
            raise ValueError(f"positive_examples are required: {proposal_id}")
        if not decision.get("negative_examples"):
            raise ValueError(f"negative_examples are required: {proposal_id}")
    elif kind == "rule":
        if not payload.get("intent") or not payload.get("rule", {}).get("pattern"):
            raise ValueError(f"rule intent/pattern is required: {proposal_id}")
        if not decision.get("positive_examples"):
            raise ValueError(f"positive_examples are required: {proposal_id}")
        if not decision.get("negative_examples"):
            raise ValueError(f"negative_examples are required: {proposal_id}")
        if decision.get("external_action_reviewed") is not True:
            raise ValueError(
                f"external_action_reviewed=true is required: {proposal_id}"
            )
    elif kind == "language_feature":
        for key in (
            "entry_id", "feature_type", "surfaces", "interpretations",
            "fallback_status", "risk_class",
        ):
            if not payload.get(key):
                raise ValueError(
                    f"language_feature.{key} is required: {proposal_id}"
                )
        if not decision.get("positive_examples"):
            raise ValueError(f"positive_examples are required: {proposal_id}")
        if not decision.get("negative_examples"):
            raise ValueError(f"negative_examples are required: {proposal_id}")
        if not decision.get("boundary_examples"):
            raise ValueError(f"boundary_examples are required: {proposal_id}")
        if payload.get("risk_class") in {"action", "social"} and (
            decision.get("external_action_reviewed") is not True
        ):
            raise ValueError(
                "external_action_reviewed=true is required for action/social "
                f"language features: {proposal_id}"
            )
        if payload.get("fallback_status") == "RESOLVED" and len(
            payload.get("interpretations", [])
        ) > 1:
            raise ValueError(
                "multi-interpretation language features cannot default to "
                f"RESOLVED: {proposal_id}"
            )
    elif kind == "synonym":
        if not payload.get("canonical") or not payload.get("surfaces"):
            raise ValueError(
                f"synonym canonical/surfaces are required: {proposal_id}"
            )
        if payload.get("ambiguous_surfaces"):
            raise ValueError(
                f"ambiguous surfaces must be resolved before approval: {proposal_id}"
            )
    elif kind == "lexicon":
        record = payload.get("record", {})
        if not record.get("lemma") or not record.get("source"):
            raise ValueError(f"lexicon lemma/source are required: {proposal_id}")
    else:
        raise ValueError(f"unsupported proposal kind: {proposal_id}: {kind}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--require-all-decided", action="store_true")
    args = parser.parse_args()

    bundle = load_bundle(args.bundle)
    decisions = load_decisions(args.decisions)
    proposal_ids = {item["proposal_id"] for item in bundle.get("proposals", [])}
    unknown = sorted(set(decisions) - proposal_ids)
    if unknown:
        raise ValueError(f"decisions reference unknown proposals: {unknown[:10]}")

    undecided: list[str] = []
    for proposal in bundle.get("proposals", []):
        proposal_id = proposal["proposal_id"]
        decision = decisions.get(proposal_id)
        if decision is None:
            undecided.append(proposal_id)
            continue
        if decision["status"] == "approved":
            validate_approval(proposal, decision)
        proposal["status"] = decision["status"]
        proposal["review"] = {
            key: value
            for key, value in decision.items()
            if key != "proposal_id"
        }
    if args.require_all_decided and undecided:
        raise ValueError(f"undecided proposals remain: {undecided[:20]}")

    statuses: dict[str, int] = {}
    for proposal in bundle.get("proposals", []):
        status = proposal.get("status", "needs_review")
        statuses[status] = statuses.get(status, 0) + 1
    bundle["status"] = "reviewed" if not undecided else "partially_reviewed"
    bundle["review_counts"] = statuses
    bundle["review_decisions_file"] = str(args.decisions)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        yaml.safe_dump(bundle, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(
        f"REVIEW OK: statuses={statuses} undecided={len(undecided)} "
        f"output={args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
