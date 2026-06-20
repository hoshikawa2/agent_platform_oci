from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("retail_mcp_server")


@mcp.tool()
def consultar_pedido(customer_id: str | None = None, order_id: str | None = None) -> dict[str, Any]:
    """Consulta dados resumidos de um pedido."""
    return {
        "customer_id": customer_id or "CUST-001",
        "order_id": order_id or "ORD-001",
        "status": "EM_TRANSPORTE",
        "valor_total": 399.90,
        "itens": [{"sku": "SKU-001", "nome": "Produto exemplo", "quantidade": 1}],
    }


@mcp.tool()
def consultar_entrega(order_id: str | None = None) -> dict[str, Any]:
    """Consulta rastreio e previsão de entrega."""
    return {
        "order_id": order_id or "ORD-001",
        "transportadora": "Entrega Express",
        "previsao": "2026-06-20",
        "status": "EM_ROTA",
    }


@mcp.tool()
def solicitar_troca(order_id: str | None = None, motivo: str | None = None) -> dict[str, Any]:
    """Abre solicitação de troca para um pedido."""
    return {
        "order_id": order_id or "ORD-001",
        "protocolo": "TROCA-123456",
        "motivo": motivo or "Não informado",
        "status": "ABERTA",
    }


@mcp.tool()
def solicitar_devolucao(order_id: str | None = None, motivo: str | None = None) -> dict[str, Any]:
    """Abre solicitação de devolução para um pedido."""
    return {
        "order_id": order_id or "ORD-001",
        "protocolo": "DEV-123456",
        "motivo": motivo or "Não informado",
        "status": "ABERTA",
    }


if __name__ == "__main__":
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = 8002

    mcp.run(transport="streamable-http")