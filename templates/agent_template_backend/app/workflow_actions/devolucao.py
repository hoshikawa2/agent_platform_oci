"""Actions de domínio permanecem no agente; o runtime está no framework."""
from agent_framework.workflows import workflow_action


@workflow_action("validar_pedido")
async def validar_pedido(params: dict, state: dict) -> dict:
    return {"valid": bool(params.get("order_id"))}


@workflow_action("registrar_devolucao")
async def registrar_devolucao(params: dict, state: dict) -> dict:
    # Substitua pela chamada real ao serviço/MCP e use chave idempotente.
    return {"protocol": f"DEV-{params['order_id']}", "status": "REQUESTED"}
