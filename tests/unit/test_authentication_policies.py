from __future__ import annotations

import base64

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from agent_framework.security import (
    AuthenticationPolicy,
    BasicAuthenticationProvider,
    NoAuthenticationProvider,
    PolicyAuthenticationMiddleware,
)


def _basic(client_id: str, secret: str) -> str:
    value = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
    return f"Basic {value}"


def test_policy_middleware_public_protected_and_default_deny():
    app = FastAPI()
    policies = [
        AuthenticationPolicy("public", NoAuthenticationProvider(), paths=("/health",)),
        AuthenticationPolicy(
            "messages",
            BasicAuthenticationProvider("tia", "plain:secret"),
            paths=("/gateway/*",),
        ),
    ]
    app.add_middleware(PolicyAuthenticationMiddleware, policies=policies)

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.get("/gateway/message")
    async def message(request: Request):
        return {"subject": request.state.auth_principal.subject}

    @app.get("/unknown")
    async def unknown():
        return {"unexpected": True}

    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/gateway/message").status_code == 401
    authenticated = client.get("/gateway/message", headers={"Authorization": _basic("tia", "secret")})
    assert authenticated.status_code == 200
    assert authenticated.json()["subject"] == "tia"
    assert client.get("/unknown").status_code == 401


def test_policy_method_filter():
    app = FastAPI()
    policies = [AuthenticationPolicy("post-only", NoAuthenticationProvider(), paths=("/resource",), methods=frozenset({"POST"}))]
    app.add_middleware(PolicyAuthenticationMiddleware, policies=policies)

    @app.get("/resource")
    async def get_resource():
        return {"method": "GET"}

    @app.post("/resource")
    async def post_resource():
        return {"method": "POST"}

    client = TestClient(app)
    assert client.post("/resource").status_code == 200
    assert client.get("/resource").status_code == 401
