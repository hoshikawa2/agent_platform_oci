from __future__ import annotations

import logging
from typing import Any

from agent_framework.identity import MCPParameterMapper

from .registry import MCPRegistry
from .client import MCPHttpClient
from .models import MCPToolResult
from .tool_policy import ToolPolicyRegistry
from agent_framework.gateways import MCPGatewayClient

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
        self.tool_policies = ToolPolicyRegistry(
            getattr(settings, "TOOL_POLICIES_PATH", None)
        )
        self.client = MCPHttpClient(timeout_seconds=settings.MCP_TOOL_TIMEOUT_SECONDS)
        self.gateway_enabled = bool(getattr(settings, "MCP_GATEWAY_ENABLED", False))
        self.gateway_agent_id = getattr(settings, "MCP_GATEWAY_AGENT_ID", "telecom_contas")
        self.gateway_tenant_id = getattr(settings, "MCP_GATEWAY_TENANT_ID", "default")
        self.gateway_client = (
            MCPGatewayClient(
                base_url=getattr(settings, "MCP_GATEWAY_URL", "http://localhost:8300"),
                token=getattr(settings, "MCP_GATEWAY_TOKEN", None),
                timeout_seconds=getattr(settings, "MCP_GATEWAY_TIMEOUT_SECONDS", settings.MCP_TOOL_TIMEOUT_SECONDS),
            )
            if self.gateway_enabled
            else None
        )
        self.parameter_mapper = MCPParameterMapper.from_yaml(
            getattr(settings, "MCP_PARAMETER_MAPPING_PATH", "./config/mcp_parameter_mapping.yaml")
        )
        logger.info(
            "MCPToolRouter carregado enabled=%s gateway_enabled=%s gateway_url=%s servers=%s tools=%s mapper=%s",
            self.enabled,
            self.gateway_enabled,
            getattr(settings, "MCP_GATEWAY_URL", None),
            list(self.registry.servers.keys()),
            list(self.registry.tools.keys()),
            getattr(settings, "MCP_PARAMETER_MAPPING_PATH", None),
        )

    def parameter_extract_rules(self, tool_name: str) -> dict[str, dict[str, Any]]:
        """Expõe extract do mcp_parameter_mapping.yaml ao runtime."""
        return self.parameter_mapper.extract_rules(tool_name)

    def resolve_execution_policy(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Retorna a política efetiva sem validar confirmação ou parâmetros."""
        legacy = self.registry.get_tool(tool_name)
        explicit = self.tool_policies.get(tool_name)
        legacy_type = getattr(legacy, "tool_type", None) if legacy else None
        operation_type = "transactional" if legacy_type in {"action", "transactional"} else "read_only"
        confirmation_required = bool(getattr(legacy, "confirmation_required", False)) if legacy else False
        required = list(getattr(legacy, "requires", None) or []) if legacy else []
        source = "tools.yaml"
        if explicit is not None:
            operation_type = explicit.operation_type
            confirmation_required = explicit.require_confirmation
            required.extend(explicit.requires)
            source = "tool_policies.yaml"
        execution = explicit.execution.model_dump() if explicit is not None else {"mode": "direct_tool", "workflow": None, "version": "active"}
        pre_validation = explicit.pre_validation.model_dump() if explicit is not None else {"enabled": False, "tool": None, "fail_open": False}
        return {
            "operation_type": operation_type,
            "require_confirmation": confirmation_required,
            "requires": list(dict.fromkeys(required)),
            "policy_source": source,
            "execution": execution,
            "pre_validation": pre_validation,
        }

    def validate_execution_policy(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> tuple[bool, str | None, dict[str, Any]]:
        """Resolve política nova + campos legados e valida a execução.

        O arquivo novo tem precedência apenas para os campos declarados por
        ferramenta. Quando ele não existe, o comportamento anterior de
        ``tools.yaml`` é preservado integralmente.
        """
        args = dict(arguments or {})
        metadata = self.resolve_execution_policy(tool_name, args)
        operation_type = metadata["operation_type"]
        confirmation_required = bool(metadata["require_confirmation"])
        required = list(metadata.get("requires") or [])
        for field_name in dict.fromkeys(required):
            if args.get(field_name) in (None, "", [], {}):
                return False, f"Campo obrigatório ausente para execução da tool: {field_name}", metadata
        confirmed = args.get("confirmed") is True or args.get("confirmation") is True
        if confirmation_required and not confirmed:
            return False, "Tool exige confirmação explícita antes da execução", metadata
        return True, None, metadata

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

        allowed, reason, policy = self.validate_execution_policy(tool_name, arguments)
        if not allowed:
            return None, {}, MCPToolResult(
                tool_name=tool_name,
                server_name=server.name,
                ok=False,
                error=reason,
                metadata={"blocked_by_policy": True, **policy},
            )

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

        async def _execute() -> MCPToolResult:
            if self.gateway_enabled and self.gateway_client:
                response = await self.gateway_client.invoke_tool(
                    tenant_id=self.gateway_tenant_id,
                    agent_id=self.gateway_agent_id,
                    channel=getattr(self.settings, "DEFAULT_CHANNEL", "web"),
                    tool_name=tool_name,
                    arguments=mapped_arguments,
                    business_context={},
                    metadata={"routed_by": "agent_framework.mcp.tool_router", "logical_server": server.name},
                )
                return MCPToolResult(
                    tool_name=tool_name,
                    server_name="mcp_gateway",
                    ok=bool(response.get("ok", False)),
                    result=response.get("data"),
                    error=response.get("error"),
                    metadata={
                        "transport": "mcp_gateway",
                        "logical_server": server.name,
                        **(response.get("metadata") or {}),
                        "cache": response.get("cache") or {},
                        "latency_ms": response.get("latency_ms"),
                    },
                )
            return await self.client.call_tool(server, tool_name, mapped_arguments)

        if self.telemetry:
            async with self.telemetry.span(
                "mcp.tool_call",
                tool_name=tool_name,
                mcp_server=("mcp_gateway" if self.gateway_enabled else server.name),
                input=mapped_arguments,
                tags=["mcp", "tool", "mcp_gateway" if self.gateway_enabled else "mcp_server"],
            ):
                result = await _execute()
                await self.telemetry.event(
                    "mcp.tool_call.completed",
                    {
                        "tool_name": tool_name,
                        "server": "mcp_gateway" if self.gateway_enabled else server.name,
                        "logical_server": server.name,
                        "ok": result.ok,
                        "error": result.error,
                    },
                )
                return result

        return await _execute()

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
