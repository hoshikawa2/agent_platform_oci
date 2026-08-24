from __future__ import annotations

from typing import Any

import httpx


class MCPGatewayClient:
    def __init__(self, base_url: str, token: str | None = None, timeout_seconds: int = 60):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_seconds = timeout_seconds

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def list_tools(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(f"{self.base_url}/v1/tools", headers=self._headers())
            response.raise_for_status()
            return response.json()

    async def invoke_tool(
        self,
        *,
        tenant_id: str,
        agent_id: str,
        channel: str | None,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        business_context: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "channel": channel,
            "tool_name": tool_name,
            "arguments": arguments or {},
            "business_context": business_context or {},
            "metadata": metadata or {},
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/v1/tools/{tool_name}/invoke",
                json=payload,
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()
