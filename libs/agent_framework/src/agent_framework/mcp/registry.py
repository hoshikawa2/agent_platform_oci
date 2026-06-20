from __future__ import annotations
from pathlib import Path
from typing import Any
import yaml
from .models import MCPServerConfig, MCPToolConfig


def _load_yaml(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

class MCPRegistry:
    """Carrega servidores e tools MCP a partir de YAML.

    O framework não acopla agente a endpoint. O agente pede uma tool lógica
    como `consultar_fatura`; o registry resolve qual MCP Server atende a tool.
    """
    def __init__(self, servers_path: str, tools_path: str):
        self.servers_path = servers_path
        self.tools_path = tools_path
        self.servers = self._load_servers()
        self.tools = self._load_tools()

    def _load_servers(self) -> dict[str, MCPServerConfig]:
        raw = _load_yaml(self.servers_path)
        servers = {}
        for name, cfg in (raw.get("servers") or {}).items():
            servers[name] = MCPServerConfig(name=name, **(cfg or {}))
        return servers

    def _load_tools(self) -> dict[str, MCPToolConfig]:
        raw = _load_yaml(self.tools_path)
        tools = {}
        for name, cfg in (raw.get("tools") or {}).items():
            tools[name] = MCPToolConfig(name=name, **(cfg or {}))
        return tools

    def get_tool(self, tool_name: str) -> MCPToolConfig | None:
        tool = self.tools.get(tool_name)
        if not tool or not tool.enabled:
            return None
        return tool

    def get_server_for_tool(self, tool_name: str) -> MCPServerConfig | None:
        tool = self.get_tool(tool_name)
        if not tool:
            return None
        server = self.servers.get(tool.mcp_server)
        if not server or not server.enabled:
            return None
        return server

    def describe_tools(self, tool_names: list[str] | None = None) -> list[dict[str, Any]]:
        names = tool_names or list(self.tools.keys())
        out = []
        for name in names:
            tool = self.get_tool(name)
            server = self.get_server_for_tool(name)
            if tool and server:
                out.append({
                    "name": tool.name,
                    "description": tool.description,
                    "server": server.name,
                    "args_schema": tool.args_schema,
                    "tool_type": tool.tool_type,
                    "requires": tool.requires,
                    "confirmation_required": tool.confirmation_required,
                    "execution_policy": tool.execution_policy,
                    "cache": tool.cache,
                })
        return out
