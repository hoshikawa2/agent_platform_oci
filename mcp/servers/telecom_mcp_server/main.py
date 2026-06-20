from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any

app = FastAPI(title="Telecom MCP Server Example")

class ToolCall(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = {}

TOOLS = {
    "consultar_fatura": {
        "description": "Consulta dados resumidos de fatura por msisdn/invoice_id.",
        "input_schema": {"msisdn": "string", "invoice_id": "string"},
    },
    "consultar_pagamentos": {
        "description": "Consulta histórico de pagamentos do cliente.",
        "input_schema": {"msisdn": "string"},
    },
    "consultar_plano": {
        "description": "Consulta plano ativo e atributos comerciais.",
        "input_schema": {"msisdn": "string", "asset_id": "string"},
    },
    "listar_servicos": {
        "description": "Lista serviços ativos e adicionais VAS.",
        "input_schema": {"msisdn": "string"},
    },
}

@app.get("/health")
async def health():
    return {"status": "ok", "server": "telecom_mcp_server"}

@app.get("/mcp/tools/list")
async def list_tools():
    return {"tools": [{"name": name, **cfg} for name, cfg in TOOLS.items()]}

@app.post("/mcp/tools/call")
async def call_tool(call: ToolCall):
    name = call.tool_name
    args = call.arguments or {}
    if name not in TOOLS:
        return {"ok": False, "error": f"Tool não encontrada: {name}"}

    if name == "consultar_fatura":
        result = {
            "invoice_id": args.get("invoice_id") or "INV-EXEMPLO-001",
            "msisdn": args.get("msisdn") or "11999999999",
            "valor_total": 249.90,
            "vencimento": "2026-06-10",
            "status": "ABERTA",
            "itens": [
                {"descricao": "Plano Controle 50GB", "valor": 149.90},
                {"descricao": "Roaming internacional", "valor": 50.00},
                {"descricao": "Serviços digitais", "valor": 50.00},
            ],
        }
    elif name == "consultar_pagamentos":
        result = {
            "msisdn": args.get("msisdn") or "11999999999",
            "pagamentos": [
                {"data": "2026-05-10", "valor": 199.90, "status": "CONFIRMADO"},
                {"data": "2026-04-10", "valor": 189.90, "status": "CONFIRMADO"},
            ],
        }
    elif name == "consultar_plano":
        result = {
            "msisdn": args.get("msisdn") or "11999999999",
            "asset_id": args.get("asset_id") or "ASSET-001",
            "plano": "Controle 50GB",
            "internet_gb": 50,
            "roaming": "Américas incluso",
            "status": "ATIVO",
        }
    elif name == "listar_servicos":
        result = {
            "msisdn": args.get("msisdn") or "11999999999",
            "servicos": [
                {"nome": "Caixa Postal", "status": "ATIVO", "valor": 0.0},
                {"nome": "TIM Segurança", "status": "ATIVO", "valor": 19.90},
            ],
        }
    else:
        result = {}

    return {"ok": True, "result": result, "metadata": {"server": "telecom", "tool": name}}
