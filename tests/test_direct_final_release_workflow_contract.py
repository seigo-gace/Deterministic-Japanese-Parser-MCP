from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _workflow_input_block(workflow: str, input_name: str) -> str:
    lines = workflow.splitlines()
    marker = f"      {input_name}:"
    start = next(index for index, line in enumerate(lines) if line == marker)
    block: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("      ") and not line.startswith("        "):
            break
        block.append(line)
    return "\n".join(block)


def test_direct_final_release_workflow_is_primary_github_managed_path() -> None:
    workflow = (ROOT / ".github/workflows/direct-final-runtime-from-release.yml").read_text(
        encoding="utf-8"
    )

    assert "Direct Final Runtime From GitHub Release" in workflow
    assert "workflow_dispatch:" in workflow
    assert "pull_request:" not in workflow
    assert "push:" not in workflow
    assert "gh release download" in workflow
    assert "GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON" not in workflow
    assert "https://www.googleapis.com/auth/drive.readonly" not in workflow
    assert "tools/compile_direct_final_runtime.py" in workflow
    assert "scripts/direct_final_deployment_contract.py" in workflow
    assert "--require-direct-final" in workflow
    assert "tests/test_direct_final_deployment_contract.py" in workflow
    assert "direct-final-runtime-github-release-${{ github.sha }}" in workflow
    assert "contents: read" in workflow
    assert "contents: write" not in workflow
    assert "git push" not in workflow
    assert "git commit" not in workflow


def test_direct_final_release_workflow_keeps_private_counts_out_of_defaults() -> None:
    workflow = (ROOT / ".github/workflows/direct-final-runtime-from-release.yml").read_text(
        encoding="utf-8"
    )

    assert "default:" not in _workflow_input_block(workflow, "release-tag")
    assert "default:" not in _workflow_input_block(workflow, "expected-records")
    assert "9852513" not in workflow
