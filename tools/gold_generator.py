#!/usr/bin/env python3
"""Generate reviewable positive, negative, quote and question Gold candidates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dictionary_supply.common import stable_id
from dictionary_supply.proposals import load_bundle


def case(
    *,
    proposal_id: str,
    variant: str,
    text: str,
    expected: dict,
    request: dict | None = None,
) -> dict:
    return {
        "id": stable_id("GOLD-CAND", proposal_id, variant),
        "proposal_id": proposal_id,
        "variant": variant,
        "text": text,
        "request": request or {},
        "expected": expected,
        "requires_review": True,
    }


def cases_for(proposal: dict) -> list[dict]:
    proposal_id = proposal["proposal_id"]
    payload = proposal.get("payload", {})
    kind = proposal.get("kind")
    output: list[dict] = []
    if kind == "metaphor":
        expression = payload.get("expression", "")
        if not expression:
            return output
        output.append(case(
            proposal_id=proposal_id,
            variant="positive",
            text=f"この状況は{expression}と言える。",
            expected={"metaphors": [expression], "unique_metaphors": True},
        ))
        output.append(case(
            proposal_id=proposal_id,
            variant="quoted",
            text=f"彼は「{expression}」と表現した。",
            expected={"metaphors": [expression], "unique_metaphors": True},
        ))
        output.append(case(
            proposal_id=proposal_id,
            variant="literal_guard",
            text=f"{expression}という語の字面だけを説明して。",
            expected={"metaphors": []},
        ))
    elif kind == "rule":
        intent = payload.get("intent")
        rule = payload.get("rule", {})
        literals = rule.get("index_literals", [])
        literal = literals[0] if literals else payload.get("marker", "")
        if not intent or not literal:
            return output
        positive = f"APIを{literal}しろ。"
        output.append(case(
            proposal_id=proposal_id,
            variant="positive",
            text=positive,
            expected={"intents": [intent]},
        ))
        output.append(case(
            proposal_id=proposal_id,
            variant="quoted_external_guard",
            text=f"「{positive}」と書かれている。",
            request={"execution_mode": "external_action"},
            expected={"intents": [intent], "execution_allowed": False},
        ))
        output.append(case(
            proposal_id=proposal_id,
            variant="question_external_guard",
            text=f"APIを{literal}しろという意味なのか？",
            request={"execution_mode": "external_action"},
            expected={"intents": [intent], "execution_allowed": False},
        ))
        output.append(case(
            proposal_id=proposal_id,
            variant="negated",
            text=f"APIを{literal}しない。",
            expected={"forbidden_task_intents": [intent]},
        ))
    elif kind == "synonym":
        canonical = payload.get("canonical")
        for surface in payload.get("surfaces", [])[:5]:
            if canonical and surface:
                output.append(case(
                    proposal_id=proposal_id,
                    variant=f"surface:{surface}",
                    text=f"{surface}について確認する。",
                    expected={
                        "canonical_equivalence": {
                            "surface": surface,
                            "canonical": canonical,
                        }
                    },
                ))
    elif kind == "lexicon":
        record = payload.get("record", {})
        lemma = record.get("lemma")
        if lemma:
            output.append(case(
                proposal_id=proposal_id,
                variant="lookup",
                text=lemma,
                expected={
                    "lexicon_record_id": record.get("record_id"),
                    "lemma": lemma,
                },
            ))
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--statuses",
        nargs="+",
        default=["needs_review", "approved"],
    )
    args = parser.parse_args()
    bundle = load_bundle(args.bundle)
    cases: list[dict] = []
    for proposal in bundle.get("proposals", []):
        if proposal.get("status") not in set(args.statuses):
            continue
        cases.extend(cases_for(proposal))
    payload = {
        "version": "2.0.0",
        "batch_id": bundle.get("batch_id"),
        "source_bundle": str(args.bundle),
        "requires_review": True,
        "cases": cases,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"GOLD GENERATOR OK: cases={len(cases)} output={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
