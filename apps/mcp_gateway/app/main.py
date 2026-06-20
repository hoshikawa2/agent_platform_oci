from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


class ToolInvokeRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)


app = FastAPI(title="Agent Framework OCI - MCP Gateway", version="0.1.0")


def load_config() -> dict[str, Any]:
    config_path = Path(os.getenv("MCP_GATEWAY_CONFIG", "config/mcp_servers.yaml"))
    if not config_path.exists():
        return {"servers": {}}
    return yaml.safe_load(config_path.read_text()) or {"servers": {}}


def find_tool(tool_name: str) -> tuple[str, dict[str, Any]] | None:
    cfg = load_config()
    for server_name, server in (cfg.get("servers") or {}).items():
        if tool_name in (server.get("tools") or []):
            return server_name, server
    return None


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "component": "mcp_gateway"}


@app.get("/tools")
def tools() -> dict[str, Any]:
    cfg = load_config()
    result = []
    for server_name, server in (cfg.get("servers") or {}).items():
        for tool in server.get("tools") or []:
            result.append({"name": tool, "server": server_name})
    return {"tools": result}


@app.post("/tools/{tool_name}/invoke")
async def invoke_tool(tool_name: str, payload: ToolInvokeRequest) -> dict[str, Any]:
    found = find_tool(tool_name)
    if not found:
        raise HTTPException(status_code=404, detail=f"Tool not registered in MCP Gateway: {tool_name}")
    server_name, server = found
    base_url = server.get("base_url")
    if not base_url:
        raise HTTPException(status_code=500, detail=f"Server {server_name} has no base_url")

    # Conventional endpoint. Concrete MCP servers may adapt this via an adapter later.
    url = f"{base_url.rstrip('/')}/tools/{tool_name}/invoke"
    try:
        async with httpx.AsyncClient(timeout=float(os.getenv("MCP_GATEWAY_TIMEOUT_SECONDS", "30"))) as client:
            resp = await client.post(url, json=payload.model_dump())
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                data.setdefault("gateway", "mcp_gateway")
                data.setdefault("server", server_name)
                data.setdefault("tool", tool_name)
            return data
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"MCP upstream request failed: {exc}") from exc
