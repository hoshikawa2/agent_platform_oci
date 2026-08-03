import asyncio
from types import SimpleNamespace

from agent_framework.judges.judge import JudgePipeline, JudgeResult


class DummyJudge:
    async def evaluate(self, question, answer, context):
        return JudgeResult(name="dummy", score=1.0, passed=True, reason="ran")


def pipeline(*, sample_rate=0.0, always=True):
    obj = object.__new__(JudgePipeline)
    obj.enabled = True
    obj.judges = [DummyJudge()]
    obj.sample_rate = sample_rate
    obj.always_run_for_transactional = always
    return obj


def test_awaiting_confirmation_bypasses_sampling():
    p = pipeline(sample_rate=0.0, always=True)
    results = asyncio.run(p.evaluate_all("devolver", "confirma?", {
        "transaction_status": "AWAITING_CONFIRMATION",
        "mcp_results": [{
            "tool_name": "solicitar_devolucao",
            "awaiting_confirmation": True,
            "transaction_status": "AWAITING_CONFIRMATION",
            "metadata": {"operation_type": "transactional"},
        }],
    }))
    assert len(results) == 1


def test_completed_transaction_bypasses_sampling_from_mcp_result():
    p = pipeline(sample_rate=0.0, always=True)
    results = asyncio.run(p.evaluate_all("sim", "protocolo DEV-1", {
        "mcp_results": [{
            "tool_name": "solicitar_devolucao",
            "ok": True,
            "metadata": {"operation_type": "transactional"},
        }],
    }))
    assert len(results) == 1


def test_non_transactional_turn_respects_zero_sample_rate():
    p = pipeline(sample_rate=0.0, always=True)
    results = asyncio.run(p.evaluate_all("pedido 123", "entregue", {
        "mcp_results": [{"tool_name": "consultar_pedido", "ok": True}],
    }))
    assert results == []


def test_transactional_detection_from_tool_policy():
    p = pipeline(sample_rate=0.0, always=True)
    results = asyncio.run(p.evaluate_all("sim", "feito", {
        "tool_policy_result": {"operation_type": "transactional"},
    }))
    assert len(results) == 1
