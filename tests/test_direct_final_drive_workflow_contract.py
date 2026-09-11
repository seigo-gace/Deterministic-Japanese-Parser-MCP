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


def test_direct_final_drive_workflow_is_manual_emergency_import_only() -> None:
    workflow = (ROOT / ".github/workflows/direct-final-runtime-from-drive.yml").read_text(
        encoding="utf-8"
    )

    assert "workflow_dispatch:" in workflow
    assert "pull_request:" not in workflow
    assert "push:" not in workflow
    assert "Direct Final Runtime Emergency Import From Drive" in workflow
    assert "GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON" in workflow
    assert "https://www.googleapis.com/auth/drive.readonly" in workflow
    assert "Drive file missing from folder" in workflow
    assert "Drive sha256 mismatch" in workflow
    assert "djpmcp.direct-runtime-final.manifest.v1" in workflow
    assert "factory_used=false" in workflow
    assert "tools/compile_direct_final_runtime.py" not in workflow
    assert "scripts/direct_final_deployment_contract.py" not in workflow
    assert "--require-direct-final" not in workflow
    assert "Build wheel with Direct Final runtime" not in workflow
    assert "direct-final-runtime-drive-release-${{ github.sha }}" not in workflow
    assert "direct-final-drive-emergency-import-report-${{ github.sha }}" in workflow
    assert "contents: read" in workflow
    assert "contents: write" not in workflow
    assert "git push" not in workflow
    assert "git commit" not in workflow


def test_direct_final_drive_workflow_keeps_private_inputs_out_of_public_defaults() -> None:
    workflow = (ROOT / ".github/workflows/direct-final-runtime-from-drive.yml").read_text(
        encoding="utf-8"
    )

    assert "default:" not in _workflow_input_block(workflow, "drive-folder-id")
    assert "default:" not in _workflow_input_block(workflow, "expected-records")
    assert '"folder_id": folder_id' not in workflow
    assert '"final_unique_runtime_entries": final_records' not in workflow
    assert '"total_bytes": total_bytes' not in workflow
    assert "Direct Final record count does not match workflow input" in workflow


def test_direct_final_source_bundle_artifact_requires_explicit_opt_in() -> None:
    workflow = (ROOT / ".github/workflows/direct-final-runtime-from-drive.yml").read_text(
        encoding="utf-8"
    )
    upload_source_input = _workflow_input_block(workflow, "upload-source-bundle")

    assert 'default: "false"' in upload_source_input
    assert "Upload staged Direct Final source bundle" in workflow
    assert "if: ${{ inputs['upload-source-bundle'] == 'true' }}" in workflow


def test_direct_final_workflow_uses_bracket_syntax_for_hyphenated_inputs() -> None:
    workflow = (ROOT / ".github/workflows/direct-final-runtime-from-drive.yml").read_text(
        encoding="utf-8"
    )

    assert "${{ inputs['drive-folder-id'] }}" in workflow
    assert "${{ inputs['expected-records'] }}" in workflow
    assert "${{ inputs['artifact-name'] }}" in workflow
    assert "${{ inputs['upload-source-bundle'] == 'true' }}" in workflow
    assert "${{ inputs.drive-folder-id }}" not in workflow
    assert "${{ inputs.expected-records }}" not in workflow
    assert "${{ inputs.artifact-name }}" not in workflow
    assert "${{ inputs.upload-source-bundle" not in workflow
