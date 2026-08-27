from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

import httpx
from fastapi import Request

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    subject: str
    scheme: str
    claims: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AuthenticationResult:
    authenticated: bool
    principal: AuthenticatedPrincipal | None = None
    error: str | None = None
    challenge: str | None = None


class AuthenticationProvider(Protocol):
    async def authenticate(self, request: Request) -> AuthenticationResult: ...


def _constant_time_equals(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def _pbkdf2_hash(secret: str, salt: str, iterations: int = 310_000) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", secret.encode(), salt.encode(), iterations)
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def verify_secret(secret: str, stored_value: str) -> bool:
    """Accepts plain:<value>, sha256:<hex>, or pbkdf2_sha256:<iterations>:<salt>:<digest>."""
    if stored_value.startswith("plain:"):
        return _constant_time_equals(secret, stored_value.removeprefix("plain:"))
    if stored_value.startswith("sha256:"):
        candidate = hashlib.sha256(secret.encode()).hexdigest()
        return _constant_time_equals(candidate, stored_value.removeprefix("sha256:"))
    if stored_value.startswith("pbkdf2_sha256:"):
        try:
            _, iterations, salt, expected = stored_value.split(":", 3)
            return _constant_time_equals(_pbkdf2_hash(secret, salt, int(iterations)), expected)
        except (ValueError, TypeError):
            return False
    return _constant_time_equals(secret, stored_value)


class NoAuthenticationProvider:
    async def authenticate(self, request: Request) -> AuthenticationResult:
        return AuthenticationResult(True, AuthenticatedPrincipal("anonymous", "none"))


class DenyAuthenticationProvider:
    async def authenticate(self, request: Request) -> AuthenticationResult:
        return AuthenticationResult(False, error="authentication_policy_not_configured")


class BasicAuthenticationProvider:
    def __init__(self, client_id: str, secret_hash: str, realm: str = "agent-api"):
        self.client_id = client_id
        self.secret_hash = secret_hash
        self.realm = realm

    async def authenticate(self, request: Request) -> AuthenticationResult:
        header = request.headers.get("authorization", "")
        if not header.lower().startswith("basic "):
            return AuthenticationResult(False, error="missing_basic_credentials", challenge=f'Basic realm="{self.realm}"')
        try:
            decoded = base64.b64decode(header.split(" ", 1)[1], validate=True).decode("utf-8")
            supplied_id, supplied_secret = decoded.split(":", 1)
        except (ValueError, UnicodeDecodeError):
            return AuthenticationResult(False, error="invalid_basic_credentials", challenge=f'Basic realm="{self.realm}"')
        valid = _constant_time_equals(supplied_id, self.client_id) and verify_secret(supplied_secret, self.secret_hash)
        if not valid:
            return AuthenticationResult(False, error="invalid_basic_credentials", challenge=f'Basic realm="{self.realm}"')
        return AuthenticationResult(True, AuthenticatedPrincipal(supplied_id, "basic"))


class ApiKeyAuthenticationProvider:
    def __init__(self, expected_hash: str, header_name: str = "x-api-key", principal: str = "api-client"):
        self.expected_hash = expected_hash
        self.header_name = header_name.lower()
        self.principal = principal

    async def authenticate(self, request: Request) -> AuthenticationResult:
        supplied = request.headers.get(self.header_name)
        if not supplied or not verify_secret(supplied, self.expected_hash):
            return AuthenticationResult(False, error="invalid_api_key")
        return AuthenticationResult(True, AuthenticatedPrincipal(self.principal, "api_key"))


class StaticBearerAuthenticationProvider:
    def __init__(self, token_hash: str, principal: str = "bearer-client"):
        self.token_hash = token_hash
        self.principal = principal

    async def authenticate(self, request: Request) -> AuthenticationResult:
        header = request.headers.get("authorization", "")
        if not header.lower().startswith("bearer "):
            return AuthenticationResult(False, error="missing_bearer_token", challenge="Bearer")
        token = header.split(" ", 1)[1]
        if not verify_secret(token, self.token_hash):
            return AuthenticationResult(False, error="invalid_bearer_token", challenge="Bearer")
        return AuthenticationResult(True, AuthenticatedPrincipal(self.principal, "bearer"))


class JwtAuthenticationProvider:
    def __init__(self, key: str, algorithms: Sequence[str], audience: str | None = None, issuer: str | None = None):
        try:
            import jwt  # type: ignore
        except ImportError as exc:
            raise RuntimeError("JWT authentication requires PyJWT[crypto]") from exc
        self.jwt = jwt
        self.key = key
        self.algorithms = list(algorithms)
        self.audience = audience
        self.issuer = issuer

    async def authenticate(self, request: Request) -> AuthenticationResult:
        header = request.headers.get("authorization", "")
        if not header.lower().startswith("bearer "):
            return AuthenticationResult(False, error="missing_bearer_token", challenge="Bearer")
        token = header.split(" ", 1)[1]
        try:
            claims = self.jwt.decode(token, self.key, algorithms=self.algorithms, audience=self.audience, issuer=self.issuer)
        except Exception as exc:
            logger.info("JWT rejected: %s", exc.__class__.__name__)
            return AuthenticationResult(False, error="invalid_jwt", challenge="Bearer")
        subject = str(claims.get("sub") or claims.get("client_id") or "jwt-client")
        return AuthenticationResult(True, AuthenticatedPrincipal(subject, "jwt", claims))


class OAuth2IntrospectionAuthenticationProvider:
    def __init__(self, introspection_url: str, client_id: str, client_secret: str, timeout_seconds: float = 5.0):
        self.introspection_url = introspection_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout_seconds = timeout_seconds

    async def authenticate(self, request: Request) -> AuthenticationResult:
        header = request.headers.get("authorization", "")
        if not header.lower().startswith("bearer "):
            return AuthenticationResult(False, error="missing_bearer_token", challenge="Bearer")
        token = header.split(" ", 1)[1]
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    self.introspection_url,
                    data={"token": token},
                    auth=(self.client_id, self.client_secret),
                    headers={"accept": "application/json"},
                )
                response.raise_for_status()
                claims = response.json()
        except (httpx.HTTPError, ValueError):
            return AuthenticationResult(False, error="introspection_unavailable", challenge="Bearer")
        if not claims.get("active") or (claims.get("exp") and int(claims["exp"]) <= int(time.time())):
            return AuthenticationResult(False, error="inactive_token", challenge="Bearer")
        subject = str(claims.get("sub") or claims.get("client_id") or claims.get("username") or "oauth-client")
        return AuthenticationResult(True, AuthenticatedPrincipal(subject, "oauth2_introspection", claims))


class TrustedProxyAuthenticationProvider:
    def __init__(self, subject_header: str = "x-authenticated-subject", shared_secret_header: str | None = None, shared_secret_hash: str | None = None):
        self.subject_header = subject_header.lower()
        self.shared_secret_header = shared_secret_header.lower() if shared_secret_header else None
        self.shared_secret_hash = shared_secret_hash

    async def authenticate(self, request: Request) -> AuthenticationResult:
        subject = request.headers.get(self.subject_header)
        if not subject:
            return AuthenticationResult(False, error="missing_trusted_subject")
        if self.shared_secret_header and self.shared_secret_hash:
            supplied = request.headers.get(self.shared_secret_header)
            if not supplied or not verify_secret(supplied, self.shared_secret_hash):
                return AuthenticationResult(False, error="invalid_proxy_signature")
        return AuthenticationResult(True, AuthenticatedPrincipal(subject, "trusted_proxy"))
