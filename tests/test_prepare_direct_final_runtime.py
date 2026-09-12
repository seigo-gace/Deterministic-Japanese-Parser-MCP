from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tests.test_direct_final_runtime_integration import _fixture
from tools.prepare_direct_final_runtime import prepare_direct_final_runtime


def test_prepare_skips_download_when_local_fixture_is_complete(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    input_root.mkdir()
    manifest_path = _fixture(input_root)
    system_root = tmp_path / "system"
    work_root = tmp_path / "work"

    with patch("tools.prepare_direct_final_runtime.subprocess.run") as run_mock:
        payload = prepare_direct_final_runtime(
            release_tag="unused-tag",
            expected_records=3,
            input_root=input_root,
            system_root=system_root,
            work_root=work_root,
            semantic_shard_size=100,
        )

    run_mock.assert_not_called()
    assert payload["downloaded"] is False
    assert payload["source_runtime_records"] == 3
    assert payload["semantic_records"] == 2
    assert Path(payload["system_root"]).is_dir()
    assert payload["DJPMCP_SYSTEM_DICT_DIR"] == payload["system_root"]


def test_prepare_exits_on_expected_records_mismatch(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    input_root.mkdir()
    _fixture(input_root)

    with pytest.raises(SystemExit, match="expected-records mismatch"):
        prepare_direct_final_runtime(
            release_tag="unused-tag",
            expected_records=999,
            input_root=input_root,
            system_root=tmp_path / "system",
            work_root=tmp_path / "work",
            semantic_shard_size=100,
        )


def test_prepare_reuses_compile_without_calling_gh(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    input_root.mkdir()
    _fixture(input_root)
    system_root = tmp_path / "system"
    work_root = tmp_path / "work"

    first = prepare_direct_final_runtime(
        release_tag="unused-tag",
        expected_records=3,
        input_root=input_root,
        system_root=system_root,
        work_root=work_root,
        semantic_shard_size=100,
    )
    assert first["reused"] is False

    with patch("tools.prepare_direct_final_runtime.subprocess.run") as run_mock:
        second = prepare_direct_final_runtime(
            release_tag="unused-tag",
            expected_records=3,
            input_root=input_root,
            system_root=system_root,
            work_root=work_root / "second",
            semantic_shard_size=100,
        )

    run_mock.assert_not_called()
    assert second["reused"] is True
    assert second["source_runtime_records"] == 3
