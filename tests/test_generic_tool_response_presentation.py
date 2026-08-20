from __future__ import annotations

from types import SimpleNamespace

from agent_framework.presentation import register_tool_response_renderer
from agent_framework.runtime.agent_runtime import AgentRuntimeMixin


class _Registry:
    def __init__(self, responses):
        self.responses = responses

    def get_tool(self, name):
        response = self.responses.get(name)
        if response is None:
            return None
        return SimpleNamespace(response=response)


class _Runtime(AgentRuntimeMixin):
    def __init__(self, responses):
        self.tool_router = SimpleNamespace(registry=_Registry(responses))

    def _mcp_rag_directive(self, results):
        return False, None

    def _mcp_llm_composition_directive(self, results):
        return False, None

    def _transactional_action_match(self, text):
        return None

    def _workflow_payload_from_tool_result(self, item):
        return None


def _result(tool, data):
    return [{"tool_name": tool, "ok": True, "result": data}]


def test_renderer_mode_uses_application_registered_renderer():
    def renderer(*, tool_name, result, state, agent_label):
        return f"[{agent_label}] {result['name']} / {state['intent']}"

    register_tool_response_renderer("test.entity", renderer)
    rt = _Runtime({"consultar_algo": {"mode": "renderer", "renderer": "test.entity"}})
    answer = rt.build_direct_mcp_answer(
        {"user_text": "consulta", "intent": "test_intent"},
        _result("consultar_algo", {"name": "OK"}),
        agent_label="TestAgent",
    )
    assert answer == "[TestAgent] OK / test_intent"


def test_missing_renderer_falls_back_without_breaking_runtime():
    rt = _Runtime({"consultar_plano": {"mode": "renderer", "renderer": "missing.renderer"}})
    answer = rt.build_direct_mcp_answer(
        {"user_text": "qual meu plano"},
        _result("consultar_plano", {"plano": "Controle", "internet_gb": 50, "status": "ATIVO"}),
        agent_label="ProductAgent",
    )
    assert answer == "[ProductAgent] Seu plano é Controle, com 50 GB e status ATIVO."


def test_no_declared_response_keeps_legacy_fallback():
    rt = _Runtime({})
    answer = rt.build_direct_mcp_answer(
        {"user_text": "qual meu plano"},
        _result("consultar_plano", {"plano": "Controle", "internet_gb": 50, "status": "ATIVO"}),
        agent_label="ProductAgent",
    )
    assert answer == "[ProductAgent] Seu plano é Controle, com 50 GB e status ATIVO."
