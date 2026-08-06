from __future__ import annotations

import base64
import hashlib

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_framework.security.authentication import ApiKeyAuthenticationProvider, BasicAuthenticationProvider
from agent_framework.security.middleware import AuthenticationMiddleware


def _basic(value: str) -> str:
    return "Basic " + base64.b64encode(value.encode()).decode()


def test_basic_authentication_protects_endpoint_and_keeps_health_public():
    app = FastAPI()
    app.add_middleware(
        AuthenticationMiddleware,
        provider=BasicAuthenticationProvider("tia", "sha256:" + hashlib.sha256(b"secret").hexdigest()),
        public_paths=["/health"],
    )

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/protected")
    async def protected():
        return {"status": "protected"}

    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/protected").status_code == 401
    assert client.get("/protected", headers={"Authorization": _basic("tia:wrong")}).status_code == 401
    assert client.get("/protected", headers={"Authorization": _basic("tia:secret")}).status_code == 200


def test_api_key_authentication():
    app = FastAPI()
    app.add_middleware(AuthenticationMiddleware, provider=ApiKeyAuthenticationProvider("plain:key-123"))

    @app.get("/protected")
    async def protected():
        return {"status": "ok"}

    client = TestClient(app)
    assert client.get("/protected").status_code == 401
    assert client.get("/protected", headers={"x-api-key": "key-123"}).status_code == 200
