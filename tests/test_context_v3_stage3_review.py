from __future__ import annotations

from functools import lru_cache
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools/review_context_v3_stage3.py"
COMPACT_TOOL_PATH = ROOT / "tools/compact_context_v3_review_packs.py"
INPUT_ROOT = ROOT / "research/context_collection/expansion_v3"


def _load_tool():
    spec = importlib.util.spec_from_file_location("context_v3_stage3", TOOL_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TOOL = _load_tool()


def _load_compact_tool():
    spec = importlib.util.spec_from_file_location(
        "compact_context_v3_review_packs", COMPACT_TOOL_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


COMPACT_TOOL = _load_compact_tool()


@lru_cache(maxsize=1)
def _inventory():
    manifest, entries = TOOL.load_entries(INPUT_ROOT)
    TOOL.validate_inventory(manifest, entries)
    return manifest, entries


@lru_cache(maxsize=1)
def _reports():
    manifest, entries = _inventory()
    return TOOL.build_reports(manifest, entries, pack_size=20)


def _queue():
    return [
        json.loads(line)
        for line in _reports()["review-queue.jsonl"].splitlines()
        if line.strip()
    ]


def test_stage3_accounts_for_every_candidate_without_promotion() -> None:
    manifest, entries = _inventory()
    reports = _reports()
    summary = json.loads(reports["summary.json"])
    queue = _queue()
    packs = [
        json.loads(line)
        for line in reports["review-packs.jsonl"].splitlines()
        if line.strip()
    ]

    assert manifest["total_entries"] == 5000
    assert len(entries) == 5000
    assert summary["total_entries"] == 5000
    assert summary["reviewed_or_approved_entries"] == 0
    assert summary["runtime_promoted_entries"] == 0
    assert len(queue) == 5000
    assert len({item["entry_id"] for item in queue}) == 5000
    assert all(item["runtime_promotion_allowed"] is False for item in queue)

    packed_ids = [
        entry_id
        for pack in packs
        for entry_id in pack["entry_ids"]
    ]
    assert len(packed_ids) == 5000
    assert len(set(packed_ids)) == 5000
    assert all(1 <= pack["entry_count"] <= 20 for pack in packs)
    assert all(pack["runtime_promotion_allowed"] is False for pack in packs)

    compact = COMPACT_TOOL.compact_pack_index(
        reports["review-packs.jsonl"],
        expected_sha256=summary["review_packs_sha256"],
    )
    compact_ids = [
        entry[0]
        for pack in compact["packs"]
        for entry in pack[3]
    ]
    assert compact["pack_count"] == len(packs)
    assert compact["entry_count"] == 5000
    assert compact_ids == packed_ids
    assert compact["runtime_promotion_allowed"] is False


def test_known_merge_era_candidate_errors_are_flagged() -> None:
    by_surface = {
        (item["category"], item["surface"]): item
        for item in _queue()
    }

    surname = by_surface[("dialect", "和田")]
    assert surname["primary_status"] == "suspected-category-mismatch"
    assert "name-or-place-candidate" in surname["flags"]

    substring = by_surface[("epistemic", "かものはし")]
    assert substring["primary_status"] == "suspected-substring-artifact"
    assert "substring-artifact" in substring["flags"]

    command = by_surface[("modality", "削除しろ")]
    assert command["primary_status"] == "blocked-source-or-license"
    assert "license-review-required" in command["flags"]
    assert "external-action-review-required" in command["flags"]

    real_modal = by_surface[("epistemic", "かもしれません")]
    assert "substring-artifact" not in real_modal["flags"]
    assert "license-review-required" in real_modal["flags"]


def test_stage3_reports_are_byte_deterministic() -> None:
    manifest, entries = _inventory()
    first = TOOL.build_reports(manifest, entries, pack_size=20)
    second = TOOL.build_reports(manifest, entries, pack_size=20)

    assert first == second
    summary = json.loads(first["summary.json"])
    assert summary["stage3_boundary"] == {
        "automatic_approval": False,
        "automatic_rejection": False,
        "human_review_required": True,
        "runtime_promotion": False,
        "semantic_completion_claim": False,
    }


def test_aggregate_mirrors_are_not_stage3_inputs() -> None:
    tool_source = TOOL_PATH.read_text(encoding="utf-8")
    assert "all_entries.jsonl" not in tool_source
    assert "all_entries.csv" not in tool_source
    manifest, entries = _inventory()
    assert manifest["total_entries"] == len(entries) == 5000
