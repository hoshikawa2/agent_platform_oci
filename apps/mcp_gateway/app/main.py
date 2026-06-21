from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


class BusinessContext(BaseModel):
    customer_key: str | None = None
    contract_key: str | None = None
    interaction_key: str | None = None
    account_key: str | None = None
    resource_key: str | None = None
    session_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolInvocation(BaseModel):
    tenant_id: str = "default"
    agent_id: str
    channel: str | None = None
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    business_context: BusinessContext = Field(default_factory=BusinessContext)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    tool_name: str
    version: str | None = None
    ok: bool
    data: Any = None
    error: str | None = None
    cache: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


def load_config() -> dict[str, Any]:
    path = Path(os.getenv("MCP_GATEWAY_CONFIG_PATH", "config/mcp_gateway.yaml"))
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


config = load_config()
cache: dict[str, tuple[float, Any]] = {}
app = FastAPI(title="Agent Platform OCI - MCP Gateway", version="1.0.0")


def audit(name: str, payload: dict[str, Any]) -> None:
    print(json.dumps({"event": name, **payload}, ensure_ascii=False, default=str))


def auth_check(authorization: str | None) -> None:
    auth = config.get("auth") or {}
    if not auth.get("enabled", False):
        return
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing MCP Gateway bearer token")
    token = authorization.split(" ", 1)[1]
    if token not in (auth.get("static_tokens") or {}):
        raise HTTPException(status_code=403, detail="Invalid MCP Gateway token")


def map_arguments(tool_name: str, args: dict[str, Any], bc: dict[str, Any]) -> dict[str, Any]:
    result = dict(args or {})
    for source, target in ((config.get("parameter_mapping") or {}).get(tool_name) or {}).items():
        if bc.get(source) is not None and target not in result:
            result[target] = bc[source]
    return result


def cache_key(tenant_id: str, agent_id: str, tool_name: str, version: str, args: dict[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(args, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    return f"mcp:{tenant_id}:{agent_id}:{tool_name}:{version}:{digest}"


async def post_with_retry(url: str, payload: dict[str, Any], timeout: int, retry: dict[str, Any]) -> Any:
    attempts = int(retry.get("max_attempts", 1)) if retry.get("enabled", False) else 1
    backoff_ms = int(retry.get("backoff_ms", 250))
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            last_exc = exc
            if attempt < attempts - 1:
                await asyncio.sleep(backoff_ms / 1000)
    raise RuntimeError(str(last_exc))


def build_server_payload(tool_name: str, args: dict[str, Any], server: dict[str, Any], tool: dict[str, Any]) -> dict[str, Any]:
    """Builds the payload expected by the downstream MCP server.

    The example servers under mcp/servers expose the framework legacy contract:
    POST /mcp/tools/call {tool_name, arguments}.  Some mocks expose direct
    tool endpoints that accept only the argument object.  The gateway supports
    both shapes through the server/tool config.
    """
    protocol = str(tool.get("protocol") or server.get("protocol") or "legacy_http")
    if protocol in {"legacy_http", "framework_http"}:
        return {"tool_name": tool_name, "arguments": args or {}}
    return args or {}


def normalize_server_response(data: Any) -> tuple[bool, Any, str | None, dict[str, Any]]:
    if isinstance(data, dict) and ("ok" in data or "result" in data or "error" in data):
        ok = bool(data.get("ok", not data.get("error")))
        return ok, data.get("result", data.get("data")), data.get("error"), data.get("metadata") or {}
    return True, data, None, {}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "mcp_gateway"}


@app.get("/ready")
async def ready():
    enabled_tools = [k for k, v in (config.get("tools") or {}).items() if v.get("enabled", True)]
    return {"status": "ready", "tools": enabled_tools}


@app.get("/v1/tools")
async def tools():
    return {"tools": [{"name": name, **cfg} for name, cfg in (config.get("tools") or {}).items()]}


@app.get("/v1/tools/{tool_name}")
async def tool_detail(tool_name: str):
    tool = (config.get("tools") or {}).get(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool not found: {tool_name}")
    return {"name": tool_name, **tool}


@app.post("/v1/tools/{tool_name}/invoke", response_model=ToolResult)
async def invoke(tool_name: str, invocation: ToolInvocation, authorization: str | None = Header(default=None)):
    started = time.perf_counter()
    auth_check(authorization)

    tool = (config.get("tools") or {}).get(tool_name)
    if not tool or not tool.get("enabled", True):
        raise HTTPException(status_code=404, detail=f"Tool not found or disabled: {tool_name}")

    if invocation.tool_name != tool_name:
        raise HTTPException(status_code=422, detail="Path tool_name and body tool_name differ")

    allowed_agents = tool.get("allowed_agents") or []
    if allowed_agents and invocation.agent_id not in allowed_agents:
        raise HTTPException(status_code=403, detail=f"Agent not allowed: {invocation.agent_id}")

    allowed_channels = tool.get("allowed_channels") or []
    if invocation.channel and allowed_channels and invocation.channel not in allowed_channels:
        raise HTTPException(status_code=403, detail=f"Channel not allowed: {invocation.channel}")

    bc = invocation.business_context.model_dump()
    missing = [k for k in tool.get("required_business_keys", []) if not bc.get(k)]
    if missing:
        raise HTTPException(status_code=422, detail={"missing_business_keys": missing})

    version = str(tool.get("version", "1.0.0"))
    args = map_arguments(tool_name, invocation.arguments, bc)

    ttl = int(tool.get("cache_ttl_seconds", 0) or 0)
    ck = None
    if tool.get("idempotent", False) and ttl > 0:
        ck = cache_key(invocation.tenant_id, invocation.agent_id, tool_name, version, args)
        cached = cache.get(ck)
        if cached and cached[0] > time.time():
            audit("mcp.cache.hit", {"tool": tool_name, "agent_id": invocation.agent_id})
            return ToolResult(
                tool_name=tool_name,
                version=version,
                ok=True,
                data=cached[1],
                cache={"hit": True, "key": ck, "ttl_seconds": ttl},
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

    server = (config.get("servers") or {}).get(tool.get("server"))
    if not server or not server.get("enabled", True):
        raise HTTPException(status_code=503, detail=f"MCP server unavailable: {tool.get('server')}")

    url = f"{server['url'].rstrip('/')}{tool.get('endpoint')}"
    audit("mcp.tool.started", {"tool": tool_name, "version": version, "agent_id": invocation.agent_id, "server": tool.get("server")})

    try:
        raw_data = await post_with_retry(
            url=url,
            payload=build_server_payload(tool_name, args, server, tool),
            timeout=int(tool.get("timeout_seconds") or server.get("timeout_seconds") or 30),
            retry=tool.get("retry") or {},
        )
        ok, data, error, server_metadata = normalize_server_response(raw_data)
        if ck and ttl > 0 and ok:
            cache[ck] = (time.time() + ttl, data)

        latency_ms = int((time.perf_counter() - started) * 1000)
        audit("mcp.tool.completed", {"tool": tool_name, "latency_ms": latency_ms, "ok": ok})
        return ToolResult(
            tool_name=tool_name,
            version=version,
            ok=ok,
            data=data,
            error=error,
            cache={"hit": False, "key": ck, "ttl_seconds": ttl},
            latency_ms=latency_ms,
            metadata={"server": tool.get("server"), **server_metadata},
        )
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        audit("mcp.tool.failed", {"tool": tool_name, "latency_ms": latency_ms, "error": str(exc)})
        return ToolResult(
            tool_name=tool_name,
            version=version,
            ok=False,
            error=str(exc),
            latency_ms=latency_ms,
            metadata={"server": tool.get("server")},
        )
