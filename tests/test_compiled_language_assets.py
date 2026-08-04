from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from deterministic_japanese_parser_mcp.language_features import (
    LanguageFeatureRuntime,
)

ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "dictionaries/system/compiled/language_features.d"


def test_compiled_language_asset_is_current() -> None:
    subprocess.run(
        [sys.executable, "tools/compile_language_features.py", "--check"],
        cwd=ROOT,
        check=True,
    )


def test_compiler_is_byte_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    for output in (first, second):
        subprocess.run(
            [
                sys.executable,
                "tools/compile_language_features.py",
                "--output-dir",
                str(output),
            ],
            cwd=ROOT,
            check=True,
        )
    first_files = {
        path.name: path.read_bytes() for path in sorted(first.iterdir())
    }
    second_files = {
        path.name: path.read_bytes() for path in sorted(second.iterdir())
    }
    assert first_files == second_files


def test_compiled_automaton_loads_without_rebuild() -> None:
    runtime = LanguageFeatureRuntime(ASSET_DIR)
    assert runtime.index.literal_count == len(runtime.surface_map)
    assert "エグい" in runtime.index.matched_literals("この完成度、エグい。")
    assert "よね" in runtime.index.matched_literals("いいよね。")
    manifest = json.loads(
        (ASSET_DIR / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["entry_count"] == len(runtime.entries)
    assert manifest["surface_count"] == len(runtime.surface_map)
    assert runtime.asset_sha256 == manifest["payload_content_sha256"]
