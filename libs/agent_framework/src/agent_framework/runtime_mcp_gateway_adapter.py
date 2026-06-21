from __future__ import annotations

from typing import Any

from agent_framework.gateways import MCPGatewayClient


class MCPGatewayRuntimeMixin:
    mcp_gateway_client: MCPGatewayClient | None = None

    async def _invoke_mcp_gateway_tool(
        self,
        state: dict[str, Any],
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.mcp_gateway_client:
            raise RuntimeError("MCP Gateway client not configured")

        result = await self.mcp_gateway_client.invoke_tool(
            tenant_id=state.get("tenant_id", "default"),
            agent_id=state.get("agent_id") or state.get("route") or "unknown",
            channel=state.get("channel"),
            tool_name=tool_name,
            arguments=arguments or {},
            business_context=state.get("business_context") or {},
            metadata={
                "session_id": state.get("session_id"),
                "conversation_key": state.get("conversation_key"),
                "trace_id": (state.get("metadata") or {}).get("trace_id"),
            },
        )

        state.setdefault("mcp_results", []).append(result)
        return result
