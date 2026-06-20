from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("telecom_mcp_server")


@mcp.tool()
def consultar_fatura(msisdn: str | None = None, invoice_id: str | None = None) -> dict[str, Any]:
    """Consulta dados resumidos de fatura por msisdn/invoice_id."""
    return {
        "invoice_id": invoice_id or "INV-EXEMPLO-001",
        "msisdn": msisdn or "11999999999",
        "valor_total": 249.90,
        "vencimento": "2026-06-10",
        "status": "ABERTA",
        "itens": [
            {"descricao": "Plano Controle 50GB", "valor": 149.90},
            {"descricao": "Roaming internacional", "valor": 50.00},
            {"descricao": "Serviços digitais", "valor": 50.00},
        ],
    }


@mcp.tool()
def consultar_pagamentos(msisdn: str | None = None) -> dict[str, Any]:
    """Consulta histórico de pagamentos do cliente."""
    return {
        "msisdn": msisdn or "11999999999",
        "pagamentos": [
            {"data": "2026-05-10", "valor": 199.90, "status": "CONFIRMADO"},
            {"data": "2026-04-10", "valor": 189.90, "status": "CONFIRMADO"},
        ],
    }


@mcp.tool()
def consultar_plano(msisdn: str | None = None, asset_id: str | None = None) -> dict[str, Any]:
    """Consulta plano ativo e atributos comerciais."""
    return {
        "msisdn": msisdn or "11999999999",
        "asset_id": asset_id or "ASSET-001",
        "plano": "Controle 50GB",
        "internet_gb": 50,
        "roaming": "Américas incluso",
        "status": "ATIVO",
    }


@mcp.tool()
def listar_servicos(msisdn: str | None = None) -> dict[str, Any]:
    """Lista serviços ativos e adicionais VAS."""
    return {
        "msisdn": msisdn or "11999999999",
        "servicos": [
            {"nome": "Caixa Postal", "status": "ATIVO", "valor": 0.0},
            {"nome": "TIM Segurança", "status": "ATIVO", "valor": 19.90},
        ],
    }


if __name__ == "__main__":
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = 8001
    mcp.run(transport="streamable-http")
