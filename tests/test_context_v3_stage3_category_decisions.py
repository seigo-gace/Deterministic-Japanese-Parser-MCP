from __future__ import annotations

from functools import lru_cache
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRIAGE_TOOL_PATH = ROOT / "tools/review_context_v3_stage3.py"
SUBSTRING_TOOL_PATH = ROOT / "tools/apply_context_v3_stage3_decisions.py"
CATEGORY_TOOL_PATH = ROOT / "tools/apply_context_v3_stage3_category_decisions.py"
INPUT_ROOT = ROOT / "research/context_collection/expansion_v3"
SUBSTRING_DECISION_PATH = (
    ROOT
    / "research/context_collection/stage3_decisions"
    / "epistemic-substring-decisions-v1.jsonl"
)
CATEGORY_DECISION_PATH = (
    ROOT
    / "research/context_collection/stage3_decisions"
    / "category-name-place-batch-001.jsonl"
)
EVIDENCE_ROOT = ROOT / "reports/context-v3-stage3"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TRIAGE_TOOL = _load_module("context_v3_stage3", TRIAGE_TOOL_PATH)
SUBSTRING_TOOL = _load_module(
    "context_v3_stage3_substring_decisions", SUBSTRING_TOOL_PATH
)
CATEGORY_TOOL = _load_module(
    "context_v3_stage3_category_decisions", CATEGORY_TOOL_PATH
)


@lru_cache(maxsize=1)
def _reports() -> dict[str, str]:
    manifest, entries = TRIAGE_TOOL.load_entries(INPUT_ROOT)
    TRIAGE_TOOL.validate_inventory(manifest, entries)
    triage = TRIAGE_TOOL.build_reports(manifest, entries, pack_size=20)

    queue_path = EVIDENCE_ROOT / ".test-review-queue.jsonl"
    substring_queue_path = EVIDENCE_ROOT / ".test-post-substring-queue.jsonl"
    queue_path.write_text(triage["review-queue.jsonl"], encoding="utf-8")
    try:
        substring_reports = SUBSTRING_TOOL.apply_decisions(
            SUBSTRING_TOOL.load_jsonl(queue_path),
            SUBSTRING_TOOL.load_jsonl(SUBSTRING_DECISION_PATH),
        )
        substring_queue_path.write_text(
            substring_reports["post-decision-queue.jsonl"],
            encoding="utf-8",
        )
        return CATEGORY_TOOL.apply_decisions(
            CATEGORY_TOOL.load_jsonl(substring_queue_path),
            CATEGORY_TOOL.load_jsonl(CATEGORY_DECISION_PATH),
            expected_batch_size=20,
        )
    finally:
        queue_path.unlink(missing_ok=True)
        substring_queue_path.unlink(missing_ok=True)


def test_category_batch_001_has_explicit_10_reject_10_retain_split() -> None:
    reports = _reports()
    summary = json.loads(reports["category-batch-001-summary.json"])
    applied = [
        json.loads(line)
        for line in reports[
            "category-batch-001-applied-decisions.jsonl"
        ].splitlines()
        if line.strip()
    ]

    assert summary["explicit_decisions"] == 20
    assert summary["decision_counts"] == {
        "reject-category-mismatch": 10,
        "retain-category-for-evidence-review": 10,
    }
    assert summary["remaining_suspected_category_mismatches"] == 1270
    assert summary["reviewed_rejected_entries_total"] == 48
    assert summary["runtime_promoted_entries"] == 0
    assert len(applied) == 20
    assert all(item["runtime_promotion_allowed"] is False for item in applied)
    assert all(item["final_runtime_approval"] is False for item in applied)


def test_modality_names_are_rejected_and_honorific_items_are_retained() -> None:
    reports = _reports()
    rows = {
        item["surface"]: item
        for item in (
            json.loads(line)
            for line in reports[
                "post-category-batch-001-queue.jsonl"
            ].splitlines()
            if line.strip()
        )
    }

    assert rows["GHQ/SCAP"]["primary_status"] == "reviewed-rejected"
    assert rows["ダマスカス"]["primary_status"] == "reviewed-rejected"
    assert (
        rows["お釈迦さま"]["primary_status"]
        == "ready-for-human-evidence-review"
    )
    assert (
        rows["よびすて"]["primary_status"]
        == "ready-for-human-evidence-review"
    )
    assert rows["お釈迦さま"]["runtime_promotion_allowed"] is False
    assert rows["よびすて"]["runtime_promotion_allowed"] is False


def test_category_batch_outputs_are_deterministic_and_published() -> None:
    first = _reports()
    second = _reports()
    assert first == second
    assert (
        EVIDENCE_ROOT / "category-batch-001-summary.json"
    ).read_text(encoding="utf-8") == first[
        "category-batch-001-summary.json"
    ]
    assert (
        EVIDENCE_ROOT / "runtime-boundary-after-category-batch-001.json"
    ).read_text(encoding="utf-8") == first[
        "runtime-boundary-after-category-batch-001.json"
    ]

    boundary = json.loads(
        first["runtime-boundary-after-category-batch-001.json"]
    )
    assert boundary["automatic_approval"] is False
    assert boundary["automatic_rejection"] is False
    assert boundary["automatic_reclassification"] is False
    assert boundary["runtime_promotion_allowed"] is False
    assert boundary["runtime_promoted_entries"] == 0
