from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_frozen_raw_workflow_does_not_run_large_generation_on_pr() -> None:
    workflow = (ROOT / ".github/workflows/public-source-harvest.yml").read_text(
        encoding="utf-8"
    )

    assert "pull_request:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "frozen-raw-pr-contract:" in workflow
    assert "if: github.event_name == 'pull_request'" in workflow
    assert "timeout-minutes: 15" in workflow
    assert "FROZEN_RAW_PR_CONTRACT_ONLY" in workflow
    assert "direct_final_runtime_required_for_completed_deployment" in workflow

    pr_contract, manual_boundary = workflow.split(
        "  legacy-frozen-raw-manual-boundary:", 1
    )
    assert "actions/download-artifact@v4" not in pr_contract
    assert "mcp-collected-raw-factory-input-v1.tar" not in pr_contract
    assert "Build assigned auxiliary source-role adapter lane shard" not in pr_contract
    assert "LEGACY_FROZEN_RAW_FACTORY_SUPERSEDED_FOR_DEPLOYMENT" in manual_boundary
    assert "Direct Final Runtime Deployment" in manual_boundary
    assert "contents: read" in workflow
    assert "contents: write" not in workflow
    assert "git push" not in workflow
    assert "git commit" not in workflow
