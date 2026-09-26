import logging

import pytest
from starlette.testclient import TestClient

from deterministic_japanese_parser_mcp.http_server import create_app


def _client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DJPMCP_HTTP_API_KEY", "test-secret")
    monkeypatch.setenv("DJPMCP_HTTP_ALLOWED_HOSTS", "testserver")
    monkeypatch.delenv("DJPMCP_HTTP_ALLOW_UNAUTHENTICATED", raising=False)
    monkeypatch.delenv("DJPMCP_HTTP_HOST", raising=False)
    return TestClient(create_app())


def test_health_and_ready_are_public(monkeypatch: pytest.MonkeyPatch):
    with _client(monkeypatch) as client:
        health = client.get("/healthz")
        ready = client.get("/readyz")

    assert health.status_code == 200
    assert health.json()["ok"] is True
    assert health.json()["service"] == "deterministic-japanese-parser"
    assert health.json()["unauthenticated"] is False
    assert ready.status_code == 200
    assert ready.json()["ok"] is True
    assert ready.json()["unauthenticated"] is False


def test_rest_analyze_requires_auth(monkeypatch: pytest.MonkeyPatch):
    with _client(monkeypatch) as client:
        response = client.post(
            "/v1/analyze",
            json={"original_text": "UIは残せ。APIだけ変更しろ。"},
        )

    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized"}


def test_rest_analyze_returns_typed_parser_response(monkeypatch: pytest.MonkeyPatch):
    text = "UIは残せ。APIだけ変更しろ。"
    with _client(monkeypatch) as client:
        response = client.post(
            "/v1/analyze",
            headers={"Authorization": "Bearer test-secret"},
            json={"original_text": text},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["original_text"] == text
    assert payload["overall_status"] in {"COMPLETE", "PARTIAL", "FAILED"}
    assert isinstance(payload["execution_allowed"], bool)
    assert isinstance(payload["meaning_graph"], dict)
    assert isinstance(payload["task_graph"]["tasks"], list)


def test_mcp_streamable_http_initialize(monkeypatch: pytest.MonkeyPatch):
    with _client(monkeypatch) as client:
        response = client.post(
            "/mcp/",
            headers={
                "Authorization": "Bearer test-secret",
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "http-test", "version": "1"},
                },
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["jsonrpc"] == "2.0"
    assert payload["id"] == 1
    assert payload["result"]["serverInfo"]["name"] == "deterministic-japanese-parser"


def test_loopback_unauthenticated_mode_is_allowed_and_visible(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    monkeypatch.delenv("DJPMCP_HTTP_API_KEY", raising=False)
    monkeypatch.setenv("DJPMCP_HTTP_ALLOW_UNAUTHENTICATED", "1")
    monkeypatch.setenv("DJPMCP_HTTP_HOST", "127.0.0.1")

    with caplog.at_level(logging.WARNING):
        with TestClient(create_app()) as client:
            health = client.get("/healthz")
            ready = client.get("/readyz")

    assert health.status_code == 200
    assert health.json()["unauthenticated"] is True
    assert ready.status_code == 200
    assert ready.json()["unauthenticated"] is True
    assert "[SECURITY WARNING] unauthenticated HTTP mode is enabled" in caplog.text


def test_ipv6_loopback_unauthenticated_mode_is_allowed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DJPMCP_HTTP_API_KEY", raising=False)
    monkeypatch.setenv("DJPMCP_HTTP_ALLOW_UNAUTHENTICATED", "true")
    monkeypatch.setenv("DJPMCP_HTTP_HOST", "::1")

    app = create_app()
    assert app is not None


def test_non_loopback_unauthenticated_mode_is_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DJPMCP_HTTP_API_KEY", raising=False)
    monkeypatch.setenv("DJPMCP_HTTP_ALLOW_UNAUTHENTICATED", "yes")
    monkeypatch.setenv("DJPMCP_HTTP_HOST", "0.0.0.0")

    with pytest.raises(RuntimeError, match="Unauthenticated HTTP mode is allowed only on loopback"):
        create_app()


def test_non_loopback_with_api_key_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    monkeypatch.setenv("DJPMCP_HTTP_API_KEY", "test-secret")
    monkeypatch.delenv("DJPMCP_HTTP_ALLOW_UNAUTHENTICATED", raising=False)
    monkeypatch.setenv("DJPMCP_HTTP_HOST", "0.0.0.0")
    monkeypatch.delenv("DJPMCP_HTTP_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("DJPMCP_HTTP_ALLOWED_ORIGINS", raising=False)

    with caplog.at_level(logging.WARNING):
        app = create_app()

    assert app is not None
    assert "DJPMCP_HTTP_ALLOWED_HOSTS is not explicitly configured" in caplog.text
    assert "DJPMCP_HTTP_ALLOWED_ORIGINS is not explicitly configured" in caplog.text
