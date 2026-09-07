from __future__ import annotations

from pathlib import Path

from scripts.direct_final_deployment_contract import evaluate_contract
from tests.test_direct_final_runtime_integration import _fixture
from tools.compile_direct_final_runtime import compile_direct_final_runtime


ROOT = Path(__file__).resolve().parents[1]


def test_checked_in_120k_snapshot_is_not_completed_semantic_deployment() -> None:
    report = evaluate_contract(
        compiled_root=ROOT / "dictionaries/system/compiled",
    )

    assert report["status"] == "PASS"
    assert report["direct_final_runtime"] is False
    assert report["completed_semantic_deployable"] is False
    assert report["open_lexicon_records"] == 120000
    assert report["warnings"]


def test_require_direct_final_rejects_lexical_snapshot() -> None:
    report = evaluate_contract(
        compiled_root=ROOT / "dictionaries/system/compiled",
        require_direct_final=True,
    )

    assert report["status"] == "FAIL"
    assert report["completed_semantic_deployable"] is False
    assert "compiled direct-final runtime" in report["failures"][0]


def test_compiled_direct_final_runtime_is_deployable(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    manifest_path = _fixture(source_root)
    system_root = tmp_path / "system"

    compile_direct_final_runtime(
        manifest_path=manifest_path,
        input_root=source_root,
        system_root=system_root,
        work_root=tmp_path / "work",
        semantic_shard_size=100,
    )

    report = evaluate_contract(
        compiled_root=system_root / "compiled",
        require_direct_final=True,
        expected_source_records=3,
    )

    assert report["status"] == "PASS"
    assert report["direct_final_runtime"] is True
    assert report["completed_semantic_deployable"] is True
    assert report["open_lexicon_records"] == 3
    assert report["semantic_records"] == 2
