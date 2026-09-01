import pytest

from agent_framework.runtime.agent_runtime import AgentRuntimeMixin


class DummyRuntime(AgentRuntimeMixin):
    def __init__(self, llm=None):
        self.llm = llm
        self.cache = None
        self.telemetry = None
        self.settings = None


class ContextFailThenOkLLM:
    def __init__(self):
        self.calls = []

    async def ainvoke(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        if len(self.calls) == 1:
            raise RuntimeError("Input length (134212) exceeds model's maximum context length (131072)")
        return "ok"


def test_compact_llm_value_drops_recursive_runtime_payload_but_keeps_business_facts():
    runtime = DummyRuntime()
    payload = {
        "result": {
            "subject": "Tamboro Mensal",
            "success": True,
            "service": {"details": {"valor": "14,99"}},
            "state": {"session": {"secret": "must-not-leak"}, "huge": "x" * 20000},
            "business_events": [{"payload": "x" * 20000}],
        }
    }
    rendered = runtime._compact_llm_value(payload, max_chars=8000)
    assert "Tamboro Mensal" in rendered
    assert "14,99" in rendered
    assert "must-not-leak" not in rendered
    assert "business_events" not in rendered
    assert len(rendered) < 9000


def test_build_messages_bounds_mcp_and_transaction_evidence():
    runtime = DummyRuntime()
    giant = {
        "tool_name": "cancelar_vas_avulso",
        "ok": True,
        "result": {
            "subject": "Tamboro Mensal",
            "validatedAmount": "14,99",
            "state": {"payload": "x" * 100000},
            "services": [{"name": f"svc-{i}", "details": {"valor": "1,00"}} for i in range(100)],
        },
    }
    state = {
        "user_text": "isso mesmo, pode cancelar",
        "sanitized_input": "isso mesmo, pode cancelar",
        "intent": "state:WAITING_CONFIRMATION",
        "route": "contestacao_agent",
        "business_context": {"customer_key": "11999999999"},
        "transaction_evidence": [{
            "transaction_id": "tx-1",
            "tool_name": "cancelar_vas_avulso",
            "arguments": {"subject": "Tamboro Mensal"},
            "status": "COMPLETED",
            "result": giant,
        }],
    }
    messages = runtime.build_messages(state, system_prompt="system", mcp_results=[giant])
    total = sum(len(m["content"]) for m in messages)
    joined = "\n".join(m["content"] for m in messages)
    assert total < 50000
    assert "Tamboro Mensal" in joined
    assert "14,99" in joined
    assert "x" * 5000 not in joined


@pytest.mark.asyncio
async def test_context_length_error_retries_once_with_compacted_messages():
    llm = ContextFailThenOkLLM()
    runtime = DummyRuntime(llm=llm)
    messages = [
        {"role": "system", "content": "s" * 30000},
        {"role": "user", "content": "u" * 120000},
    ]
    answer = await runtime._invoke_llm_cached({}, "ContestacaoAgent", messages)
    assert answer == "ok"
    assert len(llm.calls) == 2
    first_chars = sum(len(m["content"]) for m in llm.calls[0][0])
    second_chars = sum(len(m["content"]) for m in llm.calls[1][0])
    assert second_chars < first_chars
    assert second_chars <= 61000
