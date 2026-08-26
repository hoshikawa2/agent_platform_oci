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
    rt = _Runtime({"consultar_algo": {"mode": "renderer", "renderer": "test.entity", "direct": True}})
    answer = rt.build_direct_mcp_answer(
        {"user_text": "consulta", "intent": "test_intent"},
        _result("consultar_algo", {"name": "OK"}),
        agent_label="TestAgent",
    )
    assert answer == "[TestAgent] OK / test_intent"


def test_missing_renderer_does_not_break_runtime_or_use_domain_fallback():
    rt = _Runtime({"consultar_plano": {"mode": "renderer", "renderer": "missing.renderer", "direct": True}})
    answer = rt.build_direct_mcp_answer(
        {"user_text": "qual meu plano"},
        _result("consultar_plano", {"plano": "Controle", "internet_gb": 50, "status": "ATIVO"}),
        agent_label="ProductAgent",
    )
    assert answer is None


def test_renderer_without_explicit_direct_continues_to_llm_or_rag():
    def renderer(*, tool_name, result, state, agent_label):
        return f"[{agent_label}] {result['plano']}"

    register_tool_response_renderer("test.plan", renderer)
    rt = _Runtime({"consultar_plano": {"mode": "renderer", "renderer": "test.plan"}})
    answer = rt.build_direct_mcp_answer(
        {"user_text": "como funciona a tarifação do plano?"},
        _result("consultar_plano", {"plano": "Controle", "internet_gb": 50, "status": "ATIVO"}),
        agent_label="ProductAgent",
    )
    assert answer is None


def test_no_declared_response_has_no_domain_hardcoded_fallback():
    rt = _Runtime({})
    answer = rt.build_direct_mcp_answer(
        {"user_text": "qual meu plano"},
        _result("consultar_plano", {"plano": "Controle", "internet_gb": 50, "status": "ATIVO"}),
        agent_label="ProductAgent",
    )
    assert answer is None


def test_completed_workflow_does_not_replay_message_from_non_terminal_node():
    rt = AgentRuntimeMixin()
    state = {"user_text": "nao", "sanitized_input": "nao"}
    result = {
        "ok": True,
        "tool_name": "resume_workflow",
        "result": {
            "status": "COMPLETED",
            "workflow_name": "example",
            "output": {
                "format": {"mensagem": "Pergunta antiga?"},
                "decide": {"ok": True},
                "check": {"has_items": True},
            },
            "state": {"current_node": "check"},
        },
    }
    assert rt.build_direct_mcp_answer(state, [result], agent_label="Agent") is None


def test_completed_workflow_uses_only_terminal_node_explicit_message():
    rt = AgentRuntimeMixin()
    state = {"user_text": "ok", "sanitized_input": "ok"}
    result = {
        "ok": True,
        "tool_name": "resume_workflow",
        "result": {
            "status": "COMPLETED",
            "workflow_name": "example",
            "output": {
                "format": {"mensagem": "Pergunta antiga?"},
                "finish": {"mensagem": "Resposta final."},
            },
            "state": {"current_node": "finish"},
        },
    }
    assert rt.build_direct_mcp_answer(state, [result], agent_label="Agent") == "Resposta final."
