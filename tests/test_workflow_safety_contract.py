from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _workflow(name: str) -> str:
    return (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")


def _assert_read_only(name: str, *, forbidden_extra: tuple[str, ...] = ()) -> None:
    workflow = _workflow(name)
    assert "contents: read" in workflow
    forbidden = (
        "contents: write",
        "git commit",
        "git push",
        *forbidden_extra,
    )
    violations = [item for item in forbidden if item in workflow]
    assert not violations, f"{name} can mutate a branch: {violations}"


def test_open_lexicon_workflow_is_read_only_and_atomic() -> None:
    workflow = _workflow("compile-open-lexicon.yml")

    assert "branches: [main]" in workflow
    assert "diff -qr" in workflow
    assert "tests/test_repository_lexicon_integration.py" in workflow
    _assert_read_only(
        "compile-open-lexicon.yml",
        forbidden_extra=(
            "feature/import-all-dictionaries",
            "apply_stage3_lexical_graph_patch",
        ),
    )


def test_context_candidate_rebuild_is_manual_and_read_only() -> None:
    workflow = _workflow("build-context-v3.yml")

    assert "workflow_dispatch:" in workflow
    assert "pull_request:" not in workflow
    assert "push:" not in workflow
    assert "--output work/context-v3-rebuild" in workflow
    assert "research/context_collection/expansion_v3" not in workflow.split(
        "Rebuild candidates outside the repository tree", 1
    )[1]
    _assert_read_only("build-context-v3.yml")


def test_context_stage3_review_is_read_only_and_never_promotes() -> None:
    workflow = _workflow("review-context-v3-stage3.yml")

    assert "tools/review_context_v3_stage3.py" in workflow
    assert "--output-root work/context-v3-stage3" in workflow
    assert "tests/test_context_v3_stage3_review.py" in workflow
    _assert_read_only(
        "review-context-v3-stage3.yml",
        forbidden_extra=(
            "promote_language_features.py",
            "dictionaries/system/language_features.d",
        ),
    )


def test_language_asset_workflow_rebuilds_without_branch_writes() -> None:
    workflow = _workflow("language-assets.yml")

    assert "--output-dir work/language-features-compiled" in workflow
    assert "diff -qr" in workflow
    _assert_read_only("language-assets.yml")


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
