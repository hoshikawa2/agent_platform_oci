from __future__ import annotations

import os

from agent_framework.gateways import MCPGatewayClient


def build_mcp_gateway_client() -> MCPGatewayClient | None:
    if os.getenv("MCP_GATEWAY_ENABLED", "true").lower() != "true":
        return None

    return MCPGatewayClient(
        base_url=os.getenv("MCP_GATEWAY_URL", "http://localhost:8300"),
        token=os.getenv("MCP_GATEWAY_TOKEN") or None,
        timeout_seconds=int(os.getenv("MCP_GATEWAY_TIMEOUT_SECONDS", "60")),
    )
