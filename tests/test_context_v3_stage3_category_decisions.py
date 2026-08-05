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
CATEGORY_DECISION_PATHS = {
    "001": (
        ROOT
        / "research/context_collection/stage3_decisions"
        / "category-name-place-batch-001.jsonl"
    ),
    "002": (
        ROOT
        / "research/context_collection/stage3_decisions"
        / "category-name-place-batch-002.jsonl"
    ),
}
EVIDENCE_ROOT = ROOT / "reports/context-v3-stage3"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_jsonl_text(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


TRIAGE_TOOL = _load_module("context_v3_stage3", TRIAGE_TOOL_PATH)
SUBSTRING_TOOL = _load_module(
    "context_v3_stage3_substring_decisions", SUBSTRING_TOOL_PATH
)
CATEGORY_TOOL = _load_module(
    "context_v3_stage3_category_decisions", CATEGORY_TOOL_PATH
)


@lru_cache(maxsize=1)
def _reports_by_batch() -> dict[str, dict[str, str]]:
    manifest, entries = TRIAGE_TOOL.load_entries(INPUT_ROOT)
    TRIAGE_TOOL.validate_inventory(manifest, entries)
    triage = TRIAGE_TOOL.build_reports(manifest, entries, pack_size=20)

    substring_reports = SUBSTRING_TOOL.apply_decisions(
        _load_jsonl_text(triage["review-queue.jsonl"]),
        SUBSTRING_TOOL.load_jsonl(SUBSTRING_DECISION_PATH),
    )
    current_queue = _load_jsonl_text(
        substring_reports["post-decision-queue.jsonl"]
    )

    reports_by_batch: dict[str, dict[str, str]] = {}
    for batch_number in ("001", "002"):
        reports = CATEGORY_TOOL.apply_decisions(
            current_queue,
            CATEGORY_TOOL.load_jsonl(
                CATEGORY_DECISION_PATHS[batch_number]
            ),
            expected_batch_size=20,
        )
        reports_by_batch[batch_number] = reports
        current_queue = _load_jsonl_text(
            reports[f"post-category-batch-{batch_number}-queue.jsonl"]
        )
    return reports_by_batch


def test_category_batch_001_has_explicit_10_reject_10_retain_split() -> None:
    reports = _reports_by_batch()["001"]
    summary = json.loads(reports["category-batch-001-summary.json"])
    applied = _load_jsonl_text(
        reports["category-batch-001-applied-decisions.jsonl"]
    )

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


def test_category_batch_002_has_explicit_18_reject_2_retain_split() -> None:
    reports = _reports_by_batch()["002"]
    summary = json.loads(reports["category-batch-002-summary.json"])
    applied = _load_jsonl_text(
        reports["category-batch-002-applied-decisions.jsonl"]
    )

    assert summary["explicit_decisions"] == 20
    assert summary["decision_counts"] == {
        "reject-category-mismatch": 18,
        "retain-category-for-evidence-review": 2,
    }
    assert summary["remaining_suspected_category_mismatches"] == 1250
    assert summary["reviewed_rejected_entries_total"] == 66
    assert summary["runtime_promoted_entries"] == 0
    assert len(applied) == 20
    assert all(item["runtime_promotion_allowed"] is False for item in applied)
    assert all(item["final_runtime_approval"] is False for item in applied)


def test_category_batches_reject_names_and_retain_supported_features() -> None:
    batch_001_rows = {
        item["surface"]: item
        for item in _load_jsonl_text(
            _reports_by_batch()["001"][
                "post-category-batch-001-queue.jsonl"
            ]
        )
    }
    batch_002_rows = {
        item["surface"]: item
        for item in _load_jsonl_text(
            _reports_by_batch()["002"][
                "post-category-batch-002-queue.jsonl"
            ]
        )
    }

    assert batch_001_rows["GHQ/SCAP"]["primary_status"] == "reviewed-rejected"
    assert (
        batch_001_rows["お釈迦さま"]["primary_status"]
        == "ready-for-human-evidence-review"
    )
    assert batch_002_rows["奥田"]["primary_status"] == "reviewed-rejected"
    assert batch_002_rows["名古屋"]["primary_status"] == "reviewed-rejected"
    assert batch_002_rows["昭和"]["primary_status"] == "reviewed-rejected"
    assert (
        batch_002_rows["世尊"]["primary_status"]
        == "ready-for-human-evidence-review"
    )
    assert (
        batch_002_rows["鮎掛"]["primary_status"]
        == "ready-for-human-evidence-review"
    )
    assert batch_002_rows["世尊"]["runtime_promotion_allowed"] is False
    assert batch_002_rows["鮎掛"]["runtime_promotion_allowed"] is False


def test_category_batch_outputs_are_deterministic_and_published() -> None:
    first = _reports_by_batch()
    second = _reports_by_batch()
    assert first == second

    for batch_number in ("001", "002"):
        reports = first[batch_number]
        summary_name = f"category-batch-{batch_number}-summary.json"
        boundary_name = (
            f"runtime-boundary-after-category-batch-{batch_number}.json"
        )
        assert (EVIDENCE_ROOT / summary_name).read_text(
            encoding="utf-8"
        ) == reports[summary_name]
        assert (EVIDENCE_ROOT / boundary_name).read_text(
            encoding="utf-8"
        ) == reports[boundary_name]

        boundary = json.loads(reports[boundary_name])
        assert boundary["automatic_approval"] is False
        assert boundary["automatic_rejection"] is False
        assert boundary["automatic_reclassification"] is False
        assert boundary["runtime_promotion_allowed"] is False
        assert boundary["runtime_promoted_entries"] == 0
