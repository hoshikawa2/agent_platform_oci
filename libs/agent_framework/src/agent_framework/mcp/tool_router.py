from __future__ import annotations

import logging
from typing import Any

from agent_framework.identity import MCPParameterMapper

from .registry import MCPRegistry
from .client import MCPHttpClient
from .models import MCPToolResult

logger = logging.getLogger("agent_framework.mcp.tool_router")


class MCPToolRouter:
    """Roteia chamadas de tools para MCP Servers configurados.

    Também aplica, de forma centralizada, o mapper de chaves canônicas do
    framework para parâmetros reais do MCP Server. Assim os agentes podem
    trabalhar com customer_key/contract_key/etc. e o domínio TIM recebe
    msisdn/invoice_id/customer_id conforme YAML.
    """

    def __init__(self, settings, telemetry=None):
        self.settings = settings
        self.telemetry = telemetry
        self.enabled = bool(getattr(settings, "ENABLE_MCP_TOOLS", True))
        self.registry = MCPRegistry(
            settings.MCP_SERVERS_CONFIG_PATH,
            settings.TOOLS_CONFIG_PATH,
        )
        self.client = MCPHttpClient(timeout_seconds=settings.MCP_TOOL_TIMEOUT_SECONDS)
        self.parameter_mapper = MCPParameterMapper.from_yaml(
            getattr(settings, "MCP_PARAMETER_MAPPING_PATH", "./config/mcp_parameter_mapping.yaml")
        )
        logger.info(
            "MCPToolRouter carregado enabled=%s servers=%s tools=%s mapper=%s",
            self.enabled,
            list(self.registry.servers.keys()),
            list(self.registry.tools.keys()),
            getattr(settings, "MCP_PARAMETER_MAPPING_PATH", None),
        )

    def describe_tools(self, tool_names: list[str] | None = None) -> list[dict[str, Any]]:
        return self.registry.describe_tools(tool_names)

    def _mapped_arguments(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        business_context: dict[str, Any] | None = None,
        original_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        args = dict(arguments or {})
        ctx = business_context or args.get("business_context") or args.get("identity") or {}
        original = dict(original_context or {})

        # Preserva também o que veio junto dos argumentos, pois em alguns fluxos
        # o business_context vem dentro de arguments.
        for k, v in args.items():
            original.setdefault(k, v)

        mapped = self.parameter_mapper.map(
            tool_name,
            ctx,
            original_context=original,
            extra_args=args,
        )
        mapped.pop("business_context", None)
        mapped.pop("identity", None)
        return mapped

    def prepare_call(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        business_context: dict[str, Any] | None = None,
        original_context: dict[str, Any] | None = None,
    ) -> tuple[MCPServerConfig | None, dict[str, Any], MCPToolResult | None]:
        """Resolve servidor e argumentos efetivos sem executar a chamada MCP.

        Este método existe para que o runtime consiga montar cache_key antes
        da chamada real. A cache_key deve usar os argumentos finais enviados
        ao MCP Server, depois do mcp_parameter_mapping.yaml, mas antes do HTTP.
        """
        if not self.enabled:
            return None, {}, MCPToolResult(tool_name=tool_name, server_name="disabled", ok=False, error="MCP tools disabled")

        server = self.registry.get_server_for_tool(tool_name)
        if not server:
            return None, {}, MCPToolResult(tool_name=tool_name, server_name="unknown", ok=False, error="Tool/server not configured")

        mapped_arguments = self._mapped_arguments(
            tool_name,
            arguments,
            business_context=business_context,
            original_context=original_context,
        )
        return server, mapped_arguments, None

    async def call_prepared(
        self,
        tool_name: str,
        server: MCPServerConfig,
        mapped_arguments: dict[str, Any],
    ) -> MCPToolResult:
        """Executa uma chamada MCP já preparada. Não remapeia argumentos."""
        logger.info(
            "mcp.tool.mapped tool=%s server=%s keys=%s has_msisdn=%s has_invoice_id=%s",
            tool_name,
            server.name,
            sorted(mapped_arguments.keys()),
            bool(mapped_arguments.get("msisdn")),
            bool(mapped_arguments.get("invoice_id") or mapped_arguments.get("current_invoice_number")),
        )

        if self.telemetry:
            async with self.telemetry.span(
                "mcp.tool_call",
                tool_name=tool_name,
                mcp_server=server.name,
                input=mapped_arguments,
                tags=["mcp", "tool"],
            ):
                result = await self.client.call_tool(server, tool_name, mapped_arguments)
                await self.telemetry.event(
                    "mcp.tool_call.completed",
                    {
                        "tool_name": tool_name,
                        "server": server.name,
                        "ok": result.ok,
                        "error": result.error,
                    },
                )
                return result

        return await self.client.call_tool(server, tool_name, mapped_arguments)

    async def call(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        business_context: dict[str, Any] | None = None,
        original_context: dict[str, Any] | None = None,
    ) -> MCPToolResult:
        server, mapped_arguments, error = self.prepare_call(
            tool_name,
            arguments,
            business_context=business_context,
            original_context=original_context,
        )
        if error is not None:
            return error
        return await self.call_prepared(tool_name, server, mapped_arguments)


def create_mcp_tool_router(settings, telemetry=None) -> MCPToolRouter:
    return MCPToolRouter(settings, telemetry=telemetry)
