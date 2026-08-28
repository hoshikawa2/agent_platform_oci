from __future__ import annotations

from typing import Any

from agent_framework.presentation import register_tool_response_renderer


def _money_brl(value: Any) -> str:
    try:
        return f"{float(value):.2f}".replace(".", ",")
    except (TypeError, ValueError):
        return str(value)


def render_telecom_invoice(*, tool_name: str, result: dict[str, Any], state: dict[str, Any], agent_label: str) -> str | None:
    """Renderiza somente campos de negócio seguros da fatura.

    Identificadores técnicos/PII presentes no payload MCP (por exemplo msisdn,
    customer_id, document e business keys) não devem ser propagados ao usuário.
    """
    lines = [f"[{agent_label}] Dados da sua fatura:"]
    total = result.get("valor_total")
    vencimento = result.get("vencimento")
    status = result.get("status")
    if total is not None:
        lines.append(f"Valor total: R$ {_money_brl(total)}.")
    if vencimento not in (None, ""):
        lines.append(f"Vencimento: {vencimento}.")
    if status not in (None, ""):
        lines.append(f"Situação: {status}.")

    items = result.get("itens") or []
    rendered_items: list[str] = []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            description = item.get("descricao") or item.get("nome")
            value = item.get("valor")
            if description in (None, ""):
                continue
            if value is None:
                rendered_items.append(str(description))
            else:
                rendered_items.append(f"{description}: R$ {_money_brl(value)}")
    if rendered_items:
        lines.append("Itens: " + "; ".join(rendered_items) + ".")

    # Se não houver nenhum campo de negócio seguro além do cabeçalho, deixe a
    # composição pela LLM/guardrails em vez de despejar o payload bruto.
    return " ".join(lines) if len(lines) > 1 else None


def render_telecom_plan(*, tool_name: str, result: dict[str, Any], state: dict[str, Any], agent_label: str) -> str | None:
    plano = result.get("plano")
    if plano is None:
        return None
    parts = [f"[{agent_label}] Seu plano é {plano}"]
    internet_gb = result.get("internet_gb")
    status = result.get("status")
    if internet_gb is not None:
        parts.append(f"com {internet_gb} GB")
    if status is not None:
        parts.append(f"status {status}")
    return ", ".join(parts) + "."


def render_retail_order(*, tool_name: str, result: dict[str, Any], state: dict[str, Any], agent_label: str) -> str | None:
    order_id = result.get("order_id")
    status = result.get("status")
    if order_id is None or status is None:
        return None
    lines = [f"[{agent_label}] Pedido {order_id}: status {status}."]
    total = result.get("valor_total")
    if total is not None:
        lines.append(f"Valor total: R$ {_money_brl(total)}.")
    items = result.get("itens") or []
    rendered_items: list[str] = []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                value = item.get("descricao") or item.get("nome") or item.get("sku")
            else:
                value = item
            if value not in (None, ""):
                rendered_items.append(str(value))
    if rendered_items:
        lines.append("Itens: " + "; ".join(rendered_items) + ".")
    return " ".join(lines)


def render_retail_delivery(*, tool_name: str, result: dict[str, Any], state: dict[str, Any], agent_label: str) -> str | None:
    order_id = result.get("order_id")
    transportadora = result.get("transportadora")
    codigo = result.get("codigo_rastreio")
    previsao = result.get("previsao_entrega")
    if any(v is None for v in (order_id, transportadora, codigo, previsao)):
        return None
    return (
        f"[{agent_label}] Entrega do pedido {order_id}: transportadora {transportadora}, "
        f"rastreio {codigo}, previsão {previsao}."
    )


def register_tool_renderers() -> None:
    register_tool_response_renderer("telecom.invoice", render_telecom_invoice)
    register_tool_response_renderer("telecom.plan", render_telecom_plan)
    register_tool_response_renderer("retail.order", render_retail_order)
    register_tool_response_renderer("retail.delivery", render_retail_delivery)
