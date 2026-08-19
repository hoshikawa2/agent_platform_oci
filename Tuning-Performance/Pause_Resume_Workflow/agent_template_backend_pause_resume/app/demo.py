from __future__ import annotations

import asyncio
from pathlib import Path

from agent_framework.workflows import FileWorkflowRepository, WorkflowActionRegistry, WorkflowRuntime

ROOT = Path(__file__).resolve().parents[1]


def build_runtime(*, offline_test_fallback: bool = False) -> WorkflowRuntime:
    actions = WorkflowActionRegistry()

    async def preparar(params, state):
        return {"assunto": params.get("assunto") or "operação"}

    async def perguntar(params, state):
        return {"mensagem": f"Deseja confirmar {params['assunto']}?"}

    async def decidir(params, state):
        return {
            "mensagem": "Operação confirmada." if params["resposta"] == "SIM" else "Operação cancelada.",
            "confirmado": params["resposta"] == "SIM",
        }

    actions.register("preparar_operacao", preparar)
    actions.register("montar_pergunta", perguntar)
    actions.register("registrar_decisao", decidir)

    checkpointer = None
    if not offline_test_fallback:
        # Produção/exemplo real continua usando LangGraph + checkpointer. O import
        # fica aqui para que a regressão offline do repositório não dependa de rede.
        from langgraph.checkpoint.memory import MemorySaver
        checkpointer = MemorySaver()

    return WorkflowRuntime(
        FileWorkflowRepository(ROOT / "workflows"),
        actions=actions,
        checkpointer=checkpointer,
        allow_deterministic_fallback=offline_test_fallback,
    )


async def main() -> None:
    runtime = build_runtime()
    first = await runtime.arun("confirmacao", {"assunto": "a alteração do plano"})
    print(first.model_dump(mode="json"))
    assert first.status == "PAUSED"
    resumed = await runtime.aresume("confirmacao", first.execution_id, {"resposta_usuario": "sim"})
    print(resumed.model_dump(mode="json"))
    assert resumed.status == "COMPLETED"


if __name__ == "__main__":
    asyncio.run(main())
