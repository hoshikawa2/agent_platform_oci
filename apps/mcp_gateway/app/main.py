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


class DiscoveryResult(BaseModel):
    ok: bool
    servers_scanned: int = 0
    tools_discovered: int = 0
    errors: list[dict[str, Any]] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)


def load_config() -> dict[str, Any]:
    path = Path(os.getenv("MCP_GATEWAY_CONFIG_PATH", "config/mcp_gateway.yaml"))
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


config = load_config()
static_tools: dict[str, dict[str, Any]] = dict(config.get("tools") or {})
discovered_tools: dict[str, dict[str, Any]] = {}
discovery_state: dict[str, Any] = {"last_sync": None, "errors": [], "tools": []}
cache: dict[str, tuple[float, Any]] = {}
app = FastAPI(title="Agent Platform OCI - MCP Gateway", version="1.1.0")


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


def all_tools() -> dict[str, dict[str, Any]]:
    merged = dict(discovered_tools)
    # Static config wins over discovery so operators can override metadata safely.
    merged.update(static_tools)
    return merged


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


async def get_json(url: str, timeout: int) -> Any:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


def build_server_payload(tool_name: str, args: dict[str, Any], server: dict[str, Any], tool: dict[str, Any]) -> dict[str, Any]:
    """Build the payload expected by the downstream MCP server.

    Supported protocols:
    - legacy_http/framework_http: POST /mcp/tools/call with {tool_name, arguments}
    - direct_http: POST to the configured endpoint with only the argument object
    """
    protocol = str(tool.get("protocol") or server.get("protocol") or "legacy_http")
    if protocol in {"legacy_http", "framework_http", "fastmcp_http"}:
        return {"tool_name": tool_name, "arguments": args or {}}
    return args or {}


def normalize_server_response(data: Any) -> tuple[bool, Any, str | None, dict[str, Any]]:
    if isinstance(data, dict) and ("ok" in data or "result" in data or "error" in data):
        ok = bool(data.get("ok", not data.get("error")))
        return ok, data.get("result", data.get("data")), data.get("error"), data.get("metadata") or {}
    return True, data, None, {}


def _tool_name(raw: dict[str, Any]) -> str | None:
    return raw.get("name") or raw.get("tool_name") or raw.get("id")


def _tool_schema(raw: dict[str, Any]) -> dict[str, Any]:
    schema = raw.get("input_schema") or raw.get("inputSchema") or raw.get("schema") or {}
    if isinstance(schema, dict):
        return schema
    return {}


def _extract_tools_from_catalog(catalog: Any) -> list[dict[str, Any]]:
    """Normalize common MCP/FastMCP/custom catalog shapes.

    Accepted examples:
    - {"tools": [{"name": "x", "description": "...", "input_schema": {...}}]}
    - [{"name": "x", "inputSchema": {...}}]
    - {"server_id": "s", "capabilities": {"tools": [...]}}
    - {"data": {"tools": [...]}}
    """
    if isinstance(catalog, list):
        return [x for x in catalog if isinstance(x, dict)]
    if not isinstance(catalog, dict):
        return []
    if isinstance(catalog.get("tools"), list):
        return [x for x in catalog["tools"] if isinstance(x, dict)]
    data = catalog.get("data")
    if isinstance(data, dict) and isinstance(data.get("tools"), list):
        return [x for x in data["tools"] if isinstance(x, dict)]
    caps = catalog.get("capabilities")
    if isinstance(caps, dict) and isinstance(caps.get("tools"), list):
        return [x for x in caps["tools"] if isinstance(x, dict)]
    return []


def _catalog_urls(server_id: str, server: dict[str, Any]) -> list[str]:
    if server.get("manifest_url"):
        return [str(server["manifest_url"])]
    base = str(server.get("url", "")).rstrip("/")
    if server.get("catalog_endpoint"):
        return [f"{base}{server['catalog_endpoint']}"]
    discovery = config.get("discovery") or {}
    endpoints = server.get("discovery_endpoints") or discovery.get("default_catalog_endpoints") or [
        "/.well-known/mcp-server.json",
        "/manifest",
        "/mcp/tools",
        "/tools",
        "/v1/tools",
    ]
    return [f"{base}{endpoint}" for endpoint in endpoints]


def _endpoint_for_tool(server: dict[str, Any], raw_tool: dict[str, Any]) -> str:
    if raw_tool.get("endpoint"):
        return str(raw_tool["endpoint"])
    protocol = str(raw_tool.get("protocol") or server.get("protocol") or "legacy_http")
    if protocol in {"legacy_http", "framework_http", "fastmcp_http"}:
        return str(server.get("invoke_endpoint") or "/tools/call")
    name = _tool_name(raw_tool) or ""
    return str(server.get("invoke_endpoint") or f"/tools/{name}")


def normalize_discovered_tool(server_id: str, server: dict[str, Any], raw_tool: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    name = _tool_name(raw_tool)
    if not name:
        return None
    discovery = config.get("discovery") or {}
    defaults = discovery.get("tool_defaults") or {}
    tool_cfg: dict[str, Any] = {
        "version": str(raw_tool.get("version") or defaults.get("version") or "1.0.0"),
        "server": server_id,
        "endpoint": _endpoint_for_tool(server, raw_tool),
        "protocol": raw_tool.get("protocol") or server.get("protocol") or defaults.get("protocol") or "legacy_http",
        "enabled": bool(raw_tool.get("enabled", defaults.get("enabled", True))),
        "idempotent": bool(raw_tool.get("idempotent", defaults.get("idempotent", True))),
        "cache_ttl_seconds": int(raw_tool.get("cache_ttl_seconds", defaults.get("cache_ttl_seconds", 0)) or 0),
        "timeout_seconds": int(raw_tool.get("timeout_seconds", server.get("timeout_seconds", defaults.get("timeout_seconds", 30))) or 30),
        "retry": raw_tool.get("retry") or defaults.get("retry") or {"enabled": False},
        "allowed_agents": raw_tool.get("allowed_agents") or defaults.get("allowed_agents") or [],
        "allowed_channels": raw_tool.get("allowed_channels") or defaults.get("allowed_channels") or [],
        "required_business_keys": raw_tool.get("required_business_keys") or defaults.get("required_business_keys") or [],
        "description": raw_tool.get("description") or raw_tool.get("doc") or "",
        "input_schema": _tool_schema(raw_tool),
        "source": "discovery",
    }
    return name, tool_cfg


async def discover_server(server_id: str, server: dict[str, Any]) -> tuple[list[tuple[str, dict[str, Any]]], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    if not server.get("enabled", True):
        return [], []
    if not server.get("discover", False):
        return [], []
    timeout = int((config.get("discovery") or {}).get("timeout_seconds", server.get("timeout_seconds", 10)) or 10)
    for url in _catalog_urls(server_id, server):
        try:
            catalog = await get_json(url, timeout=timeout)
            raw_tools = _extract_tools_from_catalog(catalog)
            normalized = []
            for raw in raw_tools:
                item = normalize_discovered_tool(server_id, server, raw)
                if item:
                    normalized.append(item)
            if normalized:
                return normalized, errors
            errors.append({"server": server_id, "url": url, "error": "catalog returned no tools"})
        except Exception as exc:
            errors.append({"server": server_id, "url": url, "error": str(exc)})
    return [], errors


async def sync_discovery() -> DiscoveryResult:
    discovered_tools.clear()
    errors: list[dict[str, Any]] = []
    tools_count = 0
    scanned = 0
    for server_id, server in (config.get("servers") or {}).items():
        if not isinstance(server, dict) or not server.get("discover", False):
            continue
        scanned += 1
        normalized, server_errors = await discover_server(server_id, server)
        errors.extend(server_errors)
        for name, tool_cfg in normalized:
            discovered_tools[name] = tool_cfg
            tools_count += 1
    discovery_state.update({
        "last_sync": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "errors": errors,
        "tools": sorted(discovered_tools.keys()),
    })
    audit("mcp.discovery.completed", {"servers_scanned": scanned, "tools_discovered": tools_count, "errors": len(errors)})
    return DiscoveryResult(ok=not errors, servers_scanned=scanned, tools_discovered=tools_count, errors=errors, tools=sorted(discovered_tools.keys()))


@app.on_event("startup")
async def startup_discovery() -> None:
    discovery = config.get("discovery") or {}
    if discovery.get("enabled", False) and discovery.get("sync_on_startup", True):
        try:
            await sync_discovery()
        except Exception as exc:
            audit("mcp.discovery.failed", {"error": str(exc)})


@app.get("/health")
async def health():
    return {"status": "ok", "service": "mcp_gateway", "version": "1.1.0"}


@app.get("/ready")
async def ready():
    enabled_tools = [k for k, v in all_tools().items() if v.get("enabled", True)]
    return {"status": "ready", "tools": enabled_tools, "discovery": discovery_state}


@app.get("/v1/tools")
async def tools():
    return {"tools": [{"name": name, **cfg} for name, cfg in all_tools().items()]}


@app.get("/v1/tools/{tool_name}")
async def tool_detail(tool_name: str):
    tool = all_tools().get(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool not found: {tool_name}")
    return {"name": tool_name, **tool}


@app.get("/v1/discovery/servers")
async def discovery_servers():
    servers = []
    for server_id, server in (config.get("servers") or {}).items():
        servers.append({
            "id": server_id,
            "enabled": server.get("enabled", True),
            "discover": server.get("discover", False),
            "url": server.get("url"),
            "manifest_url": server.get("manifest_url"),
            "catalog_endpoint": server.get("catalog_endpoint"),
        })
    return {"servers": servers, "state": discovery_state}


@app.post("/v1/discovery/sync", response_model=DiscoveryResult)
async def discovery_sync(authorization: str | None = Header(default=None)):
    auth_check(authorization)
    return await sync_discovery()


@app.post("/v1/tools/{tool_name}/invoke", response_model=ToolResult)
async def invoke(tool_name: str, invocation: ToolInvocation, authorization: str | None = Header(default=None)):
    started = time.perf_counter()
    auth_check(authorization)

    tool = all_tools().get(tool_name)
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
            metadata={"server": tool.get("server"), "source": tool.get("source", "static"), **server_metadata},
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
            metadata={"server": tool.get("server"), "source": tool.get("source", "static")},
        )
