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
    assert "default: \"false\"" in _workflow_input_block(workflow, "projection-full-build")
    assert "9852513" not in workflow


def test_direct_final_release_workflow_prefetches_manifest_and_uses_abi_cache() -> None:
    workflow = (ROOT / ".github/workflows/direct-final-runtime-from-release.yml").read_text(
        encoding="utf-8"
    )

    assert "uses: actions/cache@v4" in workflow
    assert "Download Direct Final manifest from GitHub Release" in workflow
    assert "Verify expected-records against manifest" in workflow
    assert "Restore compiled Direct Final ABI cache" in workflow
    assert "Download Direct Final source bundle when required" in workflow
    assert "inputs['projection-full-build'] == 'true'" in workflow
    assert "direct-final-abi-${{ runner.os }}-${{ hashFiles('work/direct-final-release-input/manifest.json') }}" in workflow


def test_direct_final_release_workflow_can_run_full_projection_audit_without_new_source_path() -> None:
    workflow = (ROOT / ".github/workflows/direct-final-runtime-from-release.yml").read_text(
        encoding="utf-8"
    )

    assert "tools/compile_direct_final_japanese_function_projection.py" in workflow
    assert "Build full Japanese-function projection" in workflow
    assert "Audit 9,852,513-record projection conservation" in workflow
    assert "validate_projection_bundle" in workflow
    assert "PRAGMA integrity_check" in workflow
    assert "projected + rejected + duplicates != expected" in workflow
    assert "duplicate_record_count" in workflow
    assert "SELECT COUNT(*) FROM duplicate_record" in workflow
    assert "dangling_duplicates" in workflow
    assert "source_category_profiles" in workflow
    assert "source_payload_duplication" in workflow
    assert "work/direct-final-japanese-function-projection/manifest.json" in workflow
