from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tests.test_direct_final_runtime_integration import _fixture
from tools.compile_direct_final_runtime import _sha as compile_sha
from tools.prepare_direct_final_runtime import _gh_download, prepare_direct_final_runtime


def test_gh_download_passes_skip_existing_to_gh(tmp_path: Path) -> None:
    with (
        patch("tools.prepare_direct_final_runtime.subprocess.run") as run_mock,
        patch("tools.prepare_direct_final_runtime._extract_archives"),
    ):
        _gh_download(
            "/usr/bin/gh",
            release_tag="v1.0.0",
            repo="owner/repo",
            input_root=tmp_path / "input",
            patterns=["mcp-runtime-final-*"],
        )

    run_mock.assert_called_once()
    cmd = run_mock.call_args[0][0]
    assert "--skip-existing" in cmd


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


def test_prepare_skips_part_sha_and_gh_when_compiled_abi_is_reusable(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    input_root.mkdir()
    _fixture(input_root)
    system_root = tmp_path / "system"
    work_root = tmp_path / "work"

    prepare_direct_final_runtime(
        release_tag="unused-tag",
        expected_records=3,
        input_root=input_root,
        system_root=system_root,
        work_root=work_root,
        semantic_shard_size=100,
    )

    manifest_path = input_root / "manifest.json"
    for path in input_root.iterdir():
        if path != manifest_path:
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                import shutil

                shutil.rmtree(path)

    with (
        patch("tools.prepare_direct_final_runtime.subprocess.run") as run_mock,
        patch("tools.prepare_direct_final_runtime._inputs_match_manifest") as match_mock,
        patch("tools.prepare_direct_final_runtime._sha", wraps=compile_sha) as sha_mock,
    ):
        payload = prepare_direct_final_runtime(
            release_tag="unused-tag",
            expected_records=3,
            input_root=input_root,
            system_root=system_root,
            work_root=work_root / "reuse-only",
            semantic_shard_size=100,
        )

    run_mock.assert_not_called()
    match_mock.assert_not_called()
    assert sha_mock.call_count == 1
    assert sha_mock.call_args[0][0].name == "manifest.json"
    assert payload["reused"] is True
    assert payload["downloaded"] is False
    assert payload["source_runtime_records"] == 3


def test_companion_links_do_not_overwrite_compiled(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    input_root.mkdir()
    _fixture(input_root)
    system_root = tmp_path / "system"
    work_root = tmp_path / "work"

    prepare_direct_final_runtime(
        release_tag="unused-tag",
        expected_records=3,
        input_root=input_root,
        system_root=system_root,
        work_root=work_root,
        semantic_shard_size=100,
    )
    integration = system_root / "compiled/direct_final_integration.json"
    assert integration.is_file()
    before = integration.read_text(encoding="utf-8")

    prepare_direct_final_runtime(
        release_tag="unused-tag",
        expected_records=3,
        input_root=input_root,
        system_root=system_root,
        work_root=work_root / "again",
        semantic_shard_size=100,
    )
    assert integration.read_text(encoding="utf-8") == before


def test_companion_links_semantic_profiles(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    input_root.mkdir()
    _fixture(input_root)
    system_root = tmp_path / "system"

    payload = prepare_direct_final_runtime(
        release_tag="unused-tag",
        expected_records=3,
        input_root=input_root,
        system_root=system_root,
        work_root=tmp_path / "work",
        semantic_shard_size=100,
    )

    profiles = system_root / "semantic_profiles.yaml"
    assert profiles.exists()
    assert profiles.is_symlink()
    assert "semantic_profiles.yaml" in payload.get("companions_linked", [])
