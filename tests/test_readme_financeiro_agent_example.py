from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from types import MethodType, SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
FRAMEWORK_SRC = ROOT / "libs" / "agent_framework" / "src"
TEMPLATE_ROOT = ROOT / "templates" / "agent_template_backend"
for path in (FRAMEWORK_SRC, TEMPLATE_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


EXAMPLES = (
    ("README.md", "**COPIAR — arquivo completo canônico:**"),
    ("README_en.md", "**COPY — complete canonical file:**"),
)


class FakeLLM:
    def __init__(self):
        self.calls = 0

    async def ainvoke(self, messages, **kwargs):
        self.calls += 1
        assert messages
        assert kwargs["profile_name"] == "FinanceiroAgent"
        return "resposta documentada"


class CaptureObserver:
    def __init__(self):
        self.events: list[tuple[str, dict, str | None]] = []

    async def emit_ic(self, code, payload, component=None):
        self.events.append((code, payload, component))


def extract_documented_class(readme_name: str, marker: str):
    text = (ROOT / readme_name).read_text(encoding="utf-8")
    marked = text[text.index(marker) :]
    match = re.search(r"```python\n(.*?)\n```", marked, re.DOTALL)
    assert match, f"Bloco Python canônico ausente em {readme_name}"
    source = match.group(1)
    ast.parse(source, filename=readme_name)
    namespace: dict[str, object] = {}
    exec(compile(source, readme_name, "exec"), namespace)
    return namespace["FinanceiroAgent"], source


def make_agent(agent_class, *, observer=None):
    llm = FakeLLM()
    agent = agent_class(
        llm,
        settings=SimpleNamespace(CACHE_TTL_SECONDS=0, RAG_PROVIDER="standard"),
        observer=observer,
    )
    return agent, llm


def base_state():
    return {
        "user_text": "Qual é a situação do meu pagamento?",
        "sanitized_input": "Qual é a situação do meu pagamento?",
        "session_id": "readme-test",
        "tenant_id": "default",
        "agent_id": "financeiro_agent",
        "route": "financeiro_agent",
        "intent": "financeiro_pagamentos",
        "mcp_tools": [],
        "context": {},
    }


@pytest.mark.parametrize(("readme_name", "marker"), EXAMPLES)
def test_documented_financeiro_agent_compiles_and_uses_current_contract(readme_name, marker):
    _, source = extract_documented_class(readme_name, marker)
    required = {
        "transaction_clarification_message",
        "transaction_confirmation_message",
        "build_direct_mcp_answer",
        "prepare_memory_context",
        "build_messages",
        "transaction_state_patch",
        "rag_results",
        "IC.FINANCEIRO_RAG_CONTEXT_EVALUATED",
    }
    assert all(item in source for item in required)


@pytest.mark.asyncio
@pytest.mark.parametrize(("readme_name", "marker"), EXAMPLES)
async def test_documented_financeiro_agent_runs_normal_composition(readme_name, marker):
    agent_class, _ = extract_documented_class(readme_name, marker)
    observer = CaptureObserver()
    agent, llm = make_agent(agent_class, observer=observer)

    result = await agent.run(base_state())

    assert result["answer"] == "[FinanceiroAgent] resposta documentada"
    assert result["next_state"] == "FINANCEIRO_ACTIVE"
    assert result["mcp_results"] == []
    assert result["rag"]["status"] == "no_service"
    assert result["rag_results"][0]["agent"] == "financeiro_agent"
    assert llm.calls == 1
    codes = [event[0] for event in observer.events]
    assert "IC.FINANCEIRO_AGENT_STARTED" in codes
    assert "IC.FINANCEIRO_RAG_CONTEXT_EVALUATED" in codes
    assert "IC.FINANCEIRO_AGENT_COMPLETED" in codes


@pytest.mark.asyncio
@pytest.mark.parametrize(("readme_name", "marker"), EXAMPLES)
@pytest.mark.parametrize(
    ("method_name", "message", "expected_state"),
    (
        ("transaction_clarification_message", "Informe o contrato.", "COLLECTING_PARAMETERS"),
        ("transaction_confirmation_message", "Confirma a operação?", "AWAITING_CONFIRMATION"),
    ),
)
async def test_documented_financeiro_agent_returns_before_llm_for_transaction_prompts(
    readme_name, marker, method_name, message, expected_state
):
    agent_class, _ = extract_documented_class(readme_name, marker)
    agent, llm = make_agent(agent_class)
    state = base_state()
    state["next_state"] = expected_state

    setattr(agent, method_name, MethodType(lambda self, state: message, agent))
    result = await agent.run(state)

    assert result["answer"] == f"[FinanceiroAgent] {message}"
    assert result["next_state"] == expected_state
    assert llm.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(("readme_name", "marker"), EXAMPLES)
async def test_documented_financeiro_agent_honors_direct_mcp_response(readme_name, marker):
    agent_class, _ = extract_documented_class(readme_name, marker)
    agent, llm = make_agent(agent_class)

    async def collect(self, state):
        return [{"ok": True, "tool_name": "consultar_pagamento", "result": {"status": "PAGO"}}]

    agent._collect_tool_context = MethodType(collect, agent)
    agent.build_direct_mcp_answer = MethodType(
        lambda self, state, results, agent_label: "[FinanceiroAgent] Pagamento confirmado.", agent
    )
    result = await agent.run(base_state())

    assert result["answer"] == "[FinanceiroAgent] Pagamento confirmado."
    assert result["rag"]["reason"] == "direct_mcp_answer"
    assert llm.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(("readme_name", "marker"), EXAMPLES)
async def test_documented_financeiro_agent_emits_complete_rag_evaluation(readme_name, marker):
    agent_class, _ = extract_documented_class(readme_name, marker)
    observer = CaptureObserver()
    agent, llm = make_agent(agent_class, observer=observer)

    async def retrieve(self, state):
        return "contexto financeiro", {
            "provider": "test",
            "status": "executed",
            "attempted": True,
            "enabled": True,
            "document_count": 1,
            "graph_neighbors": 0,
            "latency_ms": 1,
            "query": state["sanitized_input"],
            "namespace": "financeiro_agent",
        }

    agent._retrieve_rag_context = MethodType(retrieve, agent)
    result = await agent.run(base_state())

    codes = [event[0] for event in observer.events]
    assert "IC.FINANCEIRO_RAG_CONTEXT_EVALUATED" in codes
    assert "IC.FINANCEIRO_RAG_CONTEXT_RETRIEVED" in codes
    assert result["rag_context"] == "contexto financeiro"
    assert llm.calls == 1
