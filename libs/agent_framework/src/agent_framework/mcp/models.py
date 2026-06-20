from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field

class MCPServerConfig(BaseModel):
    name: str
    # http = contrato legado simples do framework.
    # fastmcp/streamable_http = protocolo MCP Streamable HTTP usado pelo FastMCP.
    # sse = protocolo MCP SSE legado.
    transport: Literal["http", "fastmcp", "streamable_http", "sse"] = "http"
    endpoint: str
    enabled: bool = True
    description: str = ""

class MCPToolConfig(BaseModel):
    name: str
    description: str = ""
    mcp_server: str
    enabled: bool = True
    args_schema: dict[str, Any] = Field(default_factory=dict)

    # Política genérica opcional de execução da tool.
    # Isso permite que o framework bloqueie tools de ação antes de chamar o MCP
    # quando faltarem campos obrigatórios ou confirmação explícita.
    tool_type: str | None = None
    requires: list[str] = Field(default_factory=list)
    confirmation_required: bool = False
    execution_policy: dict[str, Any] = Field(default_factory=dict)

    # Política declarativa de cache da tool, lida diretamente de config/tools.yaml.
    # Exemplo:
    # cache:
    #   enabled: true
    #   ttl_seconds: 600
    cache: dict[str, Any] = Field(default_factory=dict)

class MCPToolResult(BaseModel):
    tool_name: str
    server_name: str
    ok: bool
    result: Any = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
