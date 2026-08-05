from __future__ import annotations

from functools import lru_cache
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRIAGE_TOOL_PATH = ROOT / "tools/review_context_v3_stage3.py"
DECISION_TOOL_PATH = ROOT / "tools/apply_context_v3_stage3_decisions.py"
INPUT_ROOT = ROOT / "research/context_collection/expansion_v3"
DECISION_PATH = (
    ROOT
    / "research/context_collection/stage3_decisions"
    / "epistemic-substring-decisions-v1.jsonl"
)
EVIDENCE_ROOT = ROOT / "reports/context-v3-stage3"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TRIAGE_TOOL = _load_module("context_v3_stage3", TRIAGE_TOOL_PATH)
DECISION_TOOL = _load_module("context_v3_stage3_decisions", DECISION_TOOL_PATH)


@lru_cache(maxsize=1)
def _reports() -> dict[str, str]:
    manifest, entries = TRIAGE_TOOL.load_entries(INPUT_ROOT)
    TRIAGE_TOOL.validate_inventory(manifest, entries)
    triage = TRIAGE_TOOL.build_reports(manifest, entries, pack_size=20)
    queue_path = EVIDENCE_ROOT / ".test-review-queue.jsonl"
    queue_path.write_text(triage["review-queue.jsonl"], encoding="utf-8")
    try:
        return DECISION_TOOL.apply_decisions(
            DECISION_TOOL.load_jsonl(queue_path),
            DECISION_TOOL.load_jsonl(DECISION_PATH),
        )
    finally:
        queue_path.unlink(missing_ok=True)


def test_substring_review_covers_all_39_flagged_candidates() -> None:
    reports = _reports()
    summary = json.loads(reports["decision-summary.json"])
    applied = [
        json.loads(line)
        for line in reports["applied-decisions.jsonl"].splitlines()
        if line.strip()
    ]

    assert summary["explicit_decisions"] == 39
    assert summary["decision_counts"] == {
        "reject-substring-artifact": 38,
        "retain-for-evidence-review": 1,
    }
    assert summary["remaining_suspected_substring_artifacts"] == 0
    assert summary["runtime_promoted_entries"] == 0
    assert len(applied) == 39
    assert all(item["runtime_promotion_allowed"] is False for item in applied)
    assert all(item["final_runtime_approval"] is False for item in applied)


def test_known_false_positive_is_rejected_and_real_kamo_is_retained() -> None:
    reports = _reports()
    rows = {
        item["surface"]: item
        for item in (
            json.loads(line)
            for line in reports["post-decision-queue.jsonl"].splitlines()
            if line.strip()
        )
    }

    assert rows["かものはし"]["primary_status"] == "reviewed-rejected"
    assert (
        rows["かものはし"]["manual_review"]["decision"]
        == "reject-substring-artifact"
    )
    assert rows["いいかも"]["primary_status"] == "ready-for-human-evidence-review"
    assert (
        rows["いいかも"]["manual_review"]["decision"]
        == "retain-for-evidence-review"
    )
    assert rows["いいかも"]["runtime_promotion_allowed"] is False


def test_decision_outputs_are_deterministic_and_published() -> None:
    first = _reports()
    second = _reports()
    assert first == second
    assert (EVIDENCE_ROOT / "decision-summary.json").read_text(
        encoding="utf-8"
    ) == first["decision-summary.json"]
    assert (EVIDENCE_ROOT / "runtime-boundary-after-decisions.json").read_text(
        encoding="utf-8"
    ) == first["runtime-boundary-after-decisions.json"]

    boundary = json.loads(first["runtime-boundary-after-decisions.json"])
    assert boundary["automatic_approval"] is False
    assert boundary["automatic_rejection"] is False
    assert boundary["runtime_promotion_allowed"] is False
    assert boundary["runtime_promoted_entries"] == 0
