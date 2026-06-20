from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any

app = FastAPI(title="Retail MCP Server Example")

class ToolCall(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = {}

TOOLS = {
    "consultar_pedido": {
        "description": "Consulta pedido de varejo por order_id/customer_id.",
        "input_schema": {"order_id": "string", "customer_id": "string"},
    },
    "consultar_entrega": {
        "description": "Consulta entrega e rastreamento do pedido.",
        "input_schema": {"order_id": "string"},
    },
    "solicitar_troca": {
        "description": "Simula abertura de solicitação de troca.",
        "input_schema": {"order_id": "string", "reason": "string"},
    },
    "solicitar_devolucao": {
        "description": "Simula abertura de solicitação de devolução.",
        "input_schema": {"order_id": "string", "reason": "string"},
    },
}

@app.get("/health")
async def health():
    return {"status": "ok", "server": "retail_mcp_server"}

@app.get("/mcp/tools/list")
async def list_tools():
    return {"tools": [{"name": name, **cfg} for name, cfg in TOOLS.items()]}

@app.post("/mcp/tools/call")
async def call_tool(call: ToolCall):
    name = call.tool_name
    args = call.arguments or {}
    if name not in TOOLS:
        return {"ok": False, "error": f"Tool não encontrada: {name}"}

    if name == "consultar_pedido":
        result = {
            "order_id": args.get("order_id") or "PED-1001",
            "customer_id": args.get("customer_id") or "CLIENTE-001",
            "status": "EM_TRANSPORTE",
            "valor_total": 349.90,
            "itens": [
                {"sku": "LIV-001", "descricao": "Livro de Arquitetura de IA", "quantidade": 1, "valor": 199.90},
                {"sku": "CAB-USB", "descricao": "Cabo USB-C", "quantidade": 1, "valor": 150.00},
            ],
        }
    elif name == "consultar_entrega":
        result = {
            "order_id": args.get("order_id") or "PED-1001",
            "transportadora": "Entrega Express",
            "codigo_rastreio": "BR123456789",
            "previsao_entrega": "2026-06-03",
            "eventos": [
                {"data": "2026-05-28", "descricao": "Pedido coletado"},
                {"data": "2026-05-29", "descricao": "Em trânsito para o centro de distribuição"},
            ],
        }
    elif name == "solicitar_troca":
        result = {
            "protocolo": "TROCA-2026-001",
            "order_id": args.get("order_id") or "PED-1001",
            "status": "ABERTO",
            "orientacao": "Aguarde instruções de postagem no e-mail cadastrado.",
        }
    elif name == "solicitar_devolucao":
        result = {
            "protocolo": "DEV-2026-001",
            "order_id": args.get("order_id") or "PED-1001",
            "status": "ABERTO",
            "orientacao": "Solicitação registrada para análise conforme política de devolução.",
        }
    else:
        result = {}

    return {"ok": True, "result": result, "metadata": {"server": "retail", "tool": name}}
