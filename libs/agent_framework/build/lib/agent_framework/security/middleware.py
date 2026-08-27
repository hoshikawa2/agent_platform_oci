from __future__ import annotations

import fnmatch
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from .authentication import AuthenticationProvider, DenyAuthenticationProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthenticationPolicy:
    name: str
    provider: AuthenticationProvider
    paths: tuple[str, ...] = ("*",)
    methods: frozenset[str] = field(default_factory=frozenset)
    required_roles: frozenset[str] = field(default_factory=frozenset)
    required_scopes: frozenset[str] = field(default_factory=frozenset)

    def matches(self, path: str, method: str) -> bool:
        method_matches = not self.methods or method.upper() in self.methods
        return method_matches and any(fnmatch.fnmatchcase(path, pattern) for pattern in self.paths)


def _claim_values(claims, names: Sequence[str]) -> set[str]:
    values: set[str] = set()
    for name in names:
        raw = claims.get(name)
        if isinstance(raw, str):
            values.update(item for item in raw.replace(",", " ").split() if item)
        elif isinstance(raw, (list, tuple, set)):
            values.update(str(item) for item in raw)
    return values


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Backward-compatible single-provider middleware."""

    def __init__(self, app, provider: AuthenticationProvider, public_paths: Iterable[str] = (), public_prefixes: Iterable[str] = ()):
        super().__init__(app)
        self.provider = provider
        self.public_paths = frozenset(public_paths)
        self.public_prefixes = tuple(public_prefixes)

    def _is_public(self, path: str) -> bool:
        return path in self.public_paths or any(path.startswith(prefix) for prefix in self.public_prefixes)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method == "OPTIONS" or self._is_public(request.url.path):
            return await call_next(request)
        return await _authenticate_request(request, call_next, self.provider)


class PolicyAuthenticationMiddleware(BaseHTTPMiddleware):
    """Selects the first matching route policy and authenticates the request."""

    def __init__(self, app, policies: Sequence[AuthenticationPolicy], default_provider: AuthenticationProvider | None = None):
        super().__init__(app)
        self.policies = tuple(policies)
        self.default_provider = default_provider or DenyAuthenticationProvider()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)
        policy = next((item for item in self.policies if item.matches(request.url.path, request.method)), None)
        if policy is None:
            return await _authenticate_request(request, call_next, self.default_provider)
        return await _authenticate_request(
            request,
            call_next,
            policy.provider,
            policy_name=policy.name,
            required_roles=policy.required_roles,
            required_scopes=policy.required_scopes,
        )


async def _authenticate_request(request: Request, call_next: RequestResponseEndpoint, provider: AuthenticationProvider, *, policy_name: str | None = None, required_roles: frozenset[str] = frozenset(), required_scopes: frozenset[str] = frozenset()) -> Response:
    result = await provider.authenticate(request)
    if not result.authenticated or result.principal is None:
        headers = {"WWW-Authenticate": result.challenge} if result.challenge else None
        return JSONResponse(status_code=401, content={"detail": "Unauthorized", "code": result.error or "unauthorized", "policy": policy_name}, headers=headers)

    roles = _claim_values(result.principal.claims, ("roles", "role", "groups"))
    scopes = _claim_values(result.principal.claims, ("scope", "scp", "scopes"))
    if required_roles and not required_roles.issubset(roles):
        return JSONResponse(status_code=403, content={"detail": "Forbidden", "code": "missing_required_role", "policy": policy_name})
    if required_scopes and not required_scopes.issubset(scopes):
        return JSONResponse(status_code=403, content={"detail": "Forbidden", "code": "missing_required_scope", "policy": policy_name})

    request.state.auth_principal = result.principal
    request.state.auth_policy = policy_name
    return await call_next(request)
