import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from semantic_holdout_contract import evaluate_holdout


def test_independent_semantic_holdout_is_at_least_95_percent():
    report = evaluate_holdout()
    evidence_path = ROOT / "reports/semantic-holdout-pytest.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    assert report["passed"], {
        "macro_accuracy": report["macro_accuracy"],
        "categories": report["categories"],
        "failed_cases": [
            {
                "case_id": item["case_id"],
                "text": item["text"],
                "evidence": item["evidence"],
            }
            for item in report["failed_cases"]
        ],
    }
    assert report["runtime_profile_independent"] is True
    assert report["macro_accuracy"] >= 0.95
    assert all(
        item["accuracy"] >= 0.90
        for item in report["categories"].values()
    )
    assert (
        report["categories"]["external_action_safety"]["accuracy"]
        == 1.0
    )
