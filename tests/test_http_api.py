import pytest
from starlette.testclient import TestClient

from deterministic_japanese_parser_mcp.http_server import create_app


def _client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DJPMCP_HTTP_API_KEY", "test-secret")
    monkeypatch.setenv("DJPMCP_HTTP_ALLOWED_HOSTS", "testserver")
    monkeypatch.delenv("DJPMCP_HTTP_ALLOW_UNAUTHENTICATED", raising=False)
    return TestClient(create_app())


def test_health_and_ready_are_public(monkeypatch: pytest.MonkeyPatch):
    with _client(monkeypatch) as client:
        health = client.get("/healthz")
        ready = client.get("/readyz")

    assert health.status_code == 200
    assert health.json()["ok"] is True
    assert health.json()["service"] == "deterministic-japanese-parser"
    assert ready.status_code == 200
    assert ready.json()["ok"] is True


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
