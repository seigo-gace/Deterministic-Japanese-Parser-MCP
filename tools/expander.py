#!/usr/bin/env python3
"""Expand review proposals with imported forms, surfaces and sense-safe aliases."""
from __future__ import annotations

import argparse
from collections import defaultdict
import copy
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dictionary_supply.common import read_jsonl
from dictionary_supply.proposals import load_bundle, PROPOSAL_SCHEMA_VERSION


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--lexicon", type=Path, action="append", default=[])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    bundle = load_bundle(args.bundle)
    by_record_id = {}
    surface_owners: dict[str, set[str]] = defaultdict(set)
    for path in args.lexicon:
        for record in read_jsonl(path):
            by_record_id[record.record_id] = record
            for surface in [record.lemma, *record.surfaces, *record.readings]:
                if surface:
                    surface_owners[surface].add(record.record_id)

    output = copy.deepcopy(bundle)
    output["schema_version"] = PROPOSAL_SCHEMA_VERSION
    output["expanded_from"] = str(args.bundle)
    output["status"] = "needs_review"
    expanded_count = 0
    for proposal in output.get("proposals", []):
        records = [
            by_record_id[item]
            for item in proposal.get("source_record_ids", [])
            if item in by_record_id
        ]
        if not records:
            continue
        payload = proposal.get("payload", {})
        if proposal.get("kind") == "metaphor":
            aliases = list(payload.get("aliases", []))
            for record in records:
                for value in [*record.surfaces, *record.readings]:
                    if (
                        value
                        and value != payload.get("expression")
                        and value not in aliases
                    ):
                        aliases.append(value)
            payload["aliases"] = aliases
            expanded_count += 1
        elif proposal.get("kind") == "synonym":
            surfaces = list(payload.get("surfaces", []))
            ambiguous: list[str] = []
            for record in records:
                for value in [*record.surfaces, *record.synonyms]:
                    if not value or value == payload.get("canonical"):
                        continue
                    if len(surface_owners.get(value, set())) > 1:
                        ambiguous.append(value)
                        continue
                    if value not in surfaces:
                        surfaces.append(value)
            payload["surfaces"] = surfaces
            payload["ambiguous_surfaces"] = sorted(set(ambiguous))
            if ambiguous:
                proposal.setdefault("review_notes", []).append(
                    "Ambiguous surfaces were excluded from automatic synonym expansion."
                )
            expanded_count += 1
        elif proposal.get("kind") == "lexicon":
            record = records[0]
            payload["record"] = record.to_dict()
            expanded_count += 1
        proposal["payload"] = payload

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        yaml.safe_dump(output, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(
        f"EXPANDER OK: expanded={expanded_count} proposals={len(output.get('proposals', []))} output={args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
