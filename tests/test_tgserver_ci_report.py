from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tools.tgserver_ci_report import build_payload, publish, severity_for_status


def test_severity_maps_ci_status_without_ambiguity() -> None:
    assert severity_for_status("success") == "info"
    assert severity_for_status("failure") == "error"
    assert severity_for_status("cancelled") == "warn"
    assert severity_for_status("skipped") == "debug"


def test_build_payload_preserves_github_evidence_identity() -> None:
    env = {
        "GITHUB_REPOSITORY": "seigo-gace/Deterministic-Japanese-Parser-MCP",
        "GITHUB_REF_NAME": "feature/example",
        "GITHUB_SHA": "abc123",
        "GITHUB_RUN_ID": "456",
        "GITHUB_RUN_ATTEMPT": "2",
        "GITHUB_WORKFLOW": "CI",
        "TGS_JOB": "test",
        "TGS_JOB_STATUS": "failure",
        "TGS_PYTHON_VERSION": "3.12",
        "TGS_PROJECT_ID": "P006",
    }
    payload = build_payload(env, now=datetime(2026, 10, 3, 15, 0, tzinfo=timezone.utc))

    assert payload["project_id"] == "P006"
    assert payload["severity"] == "error"
    assert payload["timestamp"] == "2026-10-03T15:00:00Z"
    assert "source=github-actions" in payload["message"]
    assert "repo=seigo-gace/Deterministic-Japanese-Parser-MCP" in payload["message"]
    assert "branch=feature/example" in payload["message"]
    assert "workflow=CI" in payload["message"]
    assert "run_id=456" in payload["message"]
    assert "run_attempt=2" in payload["message"]
    assert "python=3.12" in payload["message"]
    assert "status=failure" in payload["message"]
    assert payload["hint"] == "https://github.com/seigo-gace/Deterministic-Japanese-Parser-MCP/actions/runs/456"


def test_build_payload_rejects_invalid_project_id() -> None:
    with pytest.raises(ValueError):
        build_payload({"TGS_PROJECT_ID": "project-six"})


def test_publish_skips_network_when_access_secrets_are_absent() -> None:
    ok, summary = publish({"TGS_PROJECT_ID": "P006"})
    assert ok is True
    assert summary == "TGS_INGEST_CONFIGURED=FALSE"
