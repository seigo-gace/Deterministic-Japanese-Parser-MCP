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


def test_direct_final_drive_workflow_is_manual_and_gated() -> None:
    workflow = (ROOT / ".github/workflows/direct-final-runtime-from-drive.yml").read_text(
        encoding="utf-8"
    )

    assert "workflow_dispatch:" in workflow
    assert "pull_request:" not in workflow
    assert "push:" not in workflow
    assert "GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON" in workflow
    assert "https://www.googleapis.com/auth/drive.readonly" in workflow
    assert "Drive file missing from folder" in workflow
    assert "Drive sha256 mismatch" in workflow
    assert "djpmcp.direct-runtime-final.manifest.v1" in workflow
    assert "factory_used=false" in workflow
    assert "tools/compile_direct_final_runtime.py" in workflow
    assert "scripts/direct_final_deployment_contract.py" in workflow
    assert "--require-direct-final" in workflow
    assert "tests/test_direct_final_deployment_contract.py" in workflow
    assert "direct-final-runtime-drive-release-${{ github.sha }}" in workflow
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
