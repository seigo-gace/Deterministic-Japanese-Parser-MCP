from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_story_eval_workflow_is_manual_because_real_pack_artifact_expires() -> None:
    workflow = (ROOT / ".github/workflows/story-eval.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "pull_request:" not in workflow
    assert "push:" not in workflow
    assert "actions/download-artifact@v4" in workflow
    assert "run-id: 31355237121" in workflow
    assert "p0-prepared-0cf78a5eed5e093ce90f1c795801ff117d4049ba" in workflow
    assert "scripts/story_test.py" in workflow
    assert "scripts/generate_eval_package.py" in workflow
    assert "contents: read" in workflow
    assert "contents: write" not in workflow
    assert "git push" not in workflow
    assert "git commit" not in workflow
