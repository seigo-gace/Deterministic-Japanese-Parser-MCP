from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from semantic_quality_contract import evaluate_contract


def test_semantic_quality_macro_accuracy_is_at_least_95_percent():
    report = evaluate_contract()
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
    assert report["macro_accuracy"] >= 0.95
    assert all(
        item["accuracy"] >= 0.90
        for item in report["categories"].values()
    )
    assert (
        report["categories"]["external_action_safety"]["accuracy"]
        == 1.0
    )
