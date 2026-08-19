from __future__ import annotations

import pytest

from app.demo import build_runtime


@pytest.mark.asyncio
async def test_pause_resume_does_not_repeat_previous_action():
    # Regressão offline: exercita a mesma DSL/WorkflowRuntime sem exigir download
    # de LangGraph no builder. Produção continua usando build_runtime() default.
    runtime = build_runtime(offline_test_fallback=True)
    first = await runtime.arun("confirmacao", {"assunto": "o cancelamento"})
    assert first.status == "PAUSED"
    assert first.pause["expected_input"]["key"] == "resposta_usuario"
    before = [item for item in first.trace if item.get("action") == "preparar_operacao"]
    assert len(before) == 1
    resumed = await runtime.aresume("confirmacao", first.execution_id, {"resposta_usuario": "SIM"})
    assert resumed.status == "COMPLETED"
    after = [item for item in resumed.trace if item.get("action") == "preparar_operacao"]
    assert len(after) == 1
    assert resumed.state["vars"]["decidir"]["confirmado"] is True
