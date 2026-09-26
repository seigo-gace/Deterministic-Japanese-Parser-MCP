from __future__ import annotations

import contextlib
import json
import os
import secrets
from collections.abc import AsyncIterator

import uvicorn
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from .models import AnalyzeRequest
from .response_projection import project_response
from .server import SERVER_NAME, SERVER_VERSION, analyze_sync, prewarm, server

_DEFAULT_MAX_BODY_BYTES = 1_048_576
_PUBLIC_PATHS = frozenset({"/healthz", "/readyz"})


def _csv_env(name: str) -> list[str]:
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


def _truthy_env(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _positive_int_env(name: str, default: int) -> int:
    value = int(os.environ.get(name, str(default)))
    if value < 1:
        raise RuntimeError(f"{name} must be >= 1")
    return value


def _extract_api_key(headers: dict[bytes, bytes]) -> str:
    raw_authorization = headers.get(b"authorization", b"").decode("latin-1").strip()
    if raw_authorization.lower().startswith("bearer "):
        return raw_authorization[7:].strip()
    return headers.get(b"x-api-key", b"").decode("latin-1").strip()


class APIKeyMiddleware:
    """Protect parser and MCP endpoints without coupling the parser engine to deployment auth."""

    def __init__(self, app, *, api_key: str, allow_unauthenticated: bool) -> None:
        self.app = app
        self.api_key = api_key
        self.allow_unauthenticated = allow_unauthenticated
        if not self.api_key and not self.allow_unauthenticated:
            raise RuntimeError(
                "DJPMCP_HTTP_API_KEY is required. "
                "Set DJPMCP_HTTP_ALLOW_UNAUTHENTICATED=1 only for an explicitly trusted local environment."
            )

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http" or scope.get("path") in _PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return

        if self.allow_unauthenticated and not self.api_key:
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        supplied = _extract_api_key(headers)
        if not supplied or not secrets.compare_digest(supplied, self.api_key):
            response = JSONResponse(
                {"error": "unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


def create_app():
    api_key = os.environ.get("DJPMCP_HTTP_API_KEY", "").strip()
    allow_unauthenticated = _truthy_env("DJPMCP_HTTP_ALLOW_UNAUTHENTICATED", False)
    max_body_bytes = _positive_int_env("DJPMCP_HTTP_MAX_BODY_BYTES", _DEFAULT_MAX_BODY_BYTES)
    allowed_origins = _csv_env("DJPMCP_HTTP_ALLOWED_ORIGINS")
    allowed_hosts = _csv_env("DJPMCP_HTTP_ALLOWED_HOSTS") or [
        "127.0.0.1:*",
        "localhost:*",
        "[::1]:*",
    ]

    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )
    session_manager = StreamableHTTPSessionManager(
        app=server,
        json_response=True,
        stateless=True,
        security_settings=transport_security,
    )

    async def healthz(_: Request) -> JSONResponse:
        return JSONResponse(
            {
                "ok": True,
                "service": SERVER_NAME,
                "version": SERVER_VERSION,
            }
        )

    async def readyz(request: Request) -> JSONResponse:
        ready = bool(getattr(request.app.state, "ready", False))
        return JSONResponse(
            {
                "ok": ready,
                "service": SERVER_NAME,
                "version": SERVER_VERSION,
            },
            status_code=200 if ready else 503,
        )

    async def analyze(request: Request) -> JSONResponse:
        content_type = request.headers.get("content-type", "")
        if not content_type.lower().startswith("application/json"):
            return JSONResponse({"error": "content_type_must_be_application_json"}, status_code=415)

        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > max_body_bytes:
                    return JSONResponse({"error": "request_too_large"}, status_code=413)
            except ValueError:
                return JSONResponse({"error": "invalid_content_length"}, status_code=400)

        raw = await request.body()
        if len(raw) > max_body_bytes:
            return JSONResponse({"error": "request_too_large"}, status_code=413)

        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return JSONResponse({"error": "invalid_json"}, status_code=400)

        try:
            parsed = AnalyzeRequest.model_validate(payload)
        except ValidationError as error:
            return JSONResponse(
                {
                    "error": "validation_error",
                    "details": error.errors(include_url=False),
                },
                status_code=422,
            )

        response = analyze_sync(parsed)
        return JSONResponse(project_response(response, parsed.include))

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        prewarm()
        app.state.ready = True
        try:
            async with session_manager.run():
                yield
        finally:
            app.state.ready = False

    app = Starlette(
        routes=[
            Route("/healthz", endpoint=healthz, methods=["GET"]),
            Route("/readyz", endpoint=readyz, methods=["GET"]),
            Route("/v1/analyze", endpoint=analyze, methods=["POST"]),
            Mount("/mcp", app=session_manager.handle_request),
        ],
        lifespan=lifespan,
    )

    if allowed_origins:
        app = CORSMiddleware(
            app,
            allow_origins=allowed_origins,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=[
                "Accept",
                "Authorization",
                "Content-Type",
                "Last-Event-ID",
                "Mcp-Session-Id",
                "X-API-Key",
            ],
            expose_headers=["Mcp-Session-Id"],
            allow_credentials=False,
        )

    return APIKeyMiddleware(
        app,
        api_key=api_key,
        allow_unauthenticated=allow_unauthenticated,
    )


def main() -> None:
    host = os.environ.get("DJPMCP_HTTP_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = _positive_int_env("DJPMCP_HTTP_PORT", 8765)
    workers = _positive_int_env("DJPMCP_HTTP_WORKERS", 1)
    uvicorn.run(
        "deterministic_japanese_parser_mcp.http_server:create_app",
        factory=True,
        host=host,
        port=port,
        workers=workers,
        server_header=False,
        proxy_headers=False,
    )


if __name__ == "__main__":
    main()
