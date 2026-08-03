from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/dictionary_supply/wikidata-lexemes.json"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )


def test_dictionary_supply_cli_runs_from_import_to_promotion_plan(tmp_path):
    lexicon = tmp_path / "wikidata.jsonl"
    bundle = tmp_path / "bundle.yaml"
    expanded = tmp_path / "expanded.yaml"
    gold = tmp_path / "gold-candidates.json"
    decisions = tmp_path / "decisions.yaml"
    reviewed = tmp_path / "reviewed.yaml"

    imported = run(
        "tools/dictionary_supply/importers/wikidata_lexemes.py",
        "--input",
        str(FIXTURE),
        "--source-version",
        "fixture-1",
        "--output",
        str(lexicon),
    )
    assert "WIKIDATA LEXEME IMPORT OK" in imported.stdout
    assert len(lexicon.read_text(encoding="utf-8").splitlines()) == 1

    learned = run(
        "tools/learner.py",
        "--lexicon",
        str(lexicon),
        "--batch-id",
        "cli-fixture",
        "--out",
        str(bundle),
    )
    assert "LEARNER OK" in learned.stdout

    expanded_result = run(
        "tools/expander.py",
        "--bundle",
        str(bundle),
        "--lexicon",
        str(lexicon),
        "--out",
        str(expanded),
    )
    assert "EXPANDER OK" in expanded_result.stdout

    generated = run(
        "tools/gold_generator.py",
        "--bundle",
        str(expanded),
        "--out",
        str(gold),
    )
    assert "GOLD GENERATOR OK" in generated.stdout
    assert json.loads(gold.read_text(encoding="utf-8"))["cases"]

    expanded_doc = yaml.safe_load(expanded.read_text(encoding="utf-8"))
    decisions_doc = {"decisions": []}
    approved = False
    for proposal in expanded_doc["proposals"]:
        status = "rejected"
        notes = ["fixture proposal not selected"]
        if proposal["kind"] == "lexicon" and not approved:
            status = "approved"
            notes = ["fixture lexicon source and checksum reviewed"]
            approved = True
        decisions_doc["decisions"].append({
            "proposal_id": proposal["proposal_id"],
            "status": status,
            "notes": notes,
        })
    decisions.write_text(
        yaml.safe_dump(decisions_doc, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    reviewed_result = run(
        "tools/reviewer.py",
        "--bundle",
        str(expanded),
        "--decisions",
        str(decisions),
        "--require-all-decided",
        "--out",
        str(reviewed),
    )
    assert "REVIEW OK" in reviewed_result.stdout

    promotion = run(
        "tools/promoter.py",
        "--bundle",
        str(reviewed),
        "--batch-id",
        "cli-fixture",
    )
    assert "PROMOTION PLAN" in promotion.stdout
    assert "DRY RUN ONLY" in promotion.stdout
    assert "dictionaries/system/lexicon.d/cc0/cli-fixture.jsonl" in promotion.stdout
