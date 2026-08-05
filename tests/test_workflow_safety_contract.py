from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_open_lexicon_workflow_is_read_only_and_atomic() -> None:
    workflow = (
        ROOT / ".github/workflows/compile-open-lexicon.yml"
    ).read_text(encoding="utf-8")

    assert "contents: read" in workflow
    assert "branches: [main]" in workflow
    assert "diff -qr" in workflow
    assert "tests/test_repository_lexicon_integration.py" in workflow

    forbidden = (
        "contents: write",
        "git commit",
        "git push",
        "feature/import-all-dictionaries",
        "apply_stage3_lexical_graph_patch",
    )
    violations = [item for item in forbidden if item in workflow]
    assert not violations, f"branch-mutating workflow content remains: {violations}"


def test_release_wheel_contains_one_runtime_copy_of_the_120k_lexicon() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert (
        "dictionaries/system/compiled/open_lexicon/records/*.jsonl.gz"
        in pyproject
    )
    assert "dictionaries/system/compiled/open_lexicon/indexes/*.json.gz" in pyproject

    raw_wheel_sections = (
        '"share/deterministic-japanese-parser-mcp/dictionaries/system/lexicon.d/cc0"',
        '"share/deterministic-japanese-parser-mcp/dictionaries/system/lexicon.d/apache-2.0"',
        '"share/deterministic-japanese-parser-mcp/dictionaries/system/lexicon.d/cc-by-sa"',
        '"share/deterministic-japanese-parser-mcp/dictionaries/system/lexicon.d/copyleft-other"',
    )
    duplicated = [item for item in raw_wheel_sections if item in pyproject]
    assert not duplicated, f"raw source shards are duplicated into the wheel: {duplicated}"
