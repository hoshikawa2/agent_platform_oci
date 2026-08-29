from types import SimpleNamespace

import pytest

from agent_framework.routing.enterprise_router import EnterpriseRouter
from agent_framework.workflows.input_contract import match_semantic_classifier_output


ROUTING_YAML = """
router:
  fallback_agent: fallback_agent
  confidence_threshold: 0.70
intents: []
"""


class _ClassifierLLM:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    async def ainvoke(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return self.answers.pop(0)


def _router(tmp_path, answers):
    routing = tmp_path / "routing.yaml"
    routing.write_text(ROUTING_YAML, encoding="utf-8")
    settings = SimpleNamespace(
        ROUTING_CONFIG_PATH=str(routing),
        ENABLE_LLM_ROUTER=False,
        ENABLE_ROUTE_STICKINESS=False,
    )
    return EnterpriseRouter(settings, llm=_ClassifierLLM(answers))


def _state(text, allowed, prompt, *, history=None, include_relevant_context=False):
    return {
        "user_text": text,
        "sanitized_input": text,
        "route": "owner_agent",
        "active_agent": "owner_agent",
        "intent": "owner_intent",
        "route_decision": {"route": "owner_agent", "agent": "owner_agent", "intent": "owner_intent"},
        "pending_domain_workflow": {
            "workflow_name": "example",
            "execution_id": "exec-1",
            "resume_tool": "retomar_workflow",
            "owner_agent": "owner_agent",
            "owner_intent": "owner_intent",
            "pause": {
                "prompt": "Pergunta pendente",
                "expected_input": {
                    "key": "resposta_usuario",
                    "allowed_values": allowed,
                    "normalize": "upper_strip",
                    "reprompt": "Escolha novamente.",
                    "semantic_classifier": {
                        "enabled": True,
                        "include_relevant_context": include_relevant_context,
                        "prompt": prompt,
                    },
                },
            },
        },
        "history": list(history or []),
    }


@pytest.mark.asyncio
async def test_semantic_classifier_maps_acknowledgement_to_configured_option(tmp_path):
    router = _router(tmp_path, ["SIM"])
    decision = await router.route(_state("legal!", ["SIM", "NAO"], "Classifique {{ user_input }} em {{ allowed_values }}"))
    assert decision.metadata["workflow_semantic_classifier"] is True
    assert decision.metadata["normalized_input"] == "SIM"
    assert decision.metadata["original_input"] == "legal!"


@pytest.mark.asyncio
async def test_semantic_classifier_can_map_forward_fact_question_to_nao(tmp_path):
    router = _router(tmp_path, ["NAO"])
    decision = await router.route(_state("então minha fatura ficaria R$ 275,00, certo?", ["SIM", "NAO"], "Hipóteses => NAO. Opções {{ allowed_values }}"))
    assert decision.metadata["normalized_input"] == "NAO"
    assert decision.metadata["original_input"].startswith("então minha fatura")


@pytest.mark.asyncio
async def test_semantic_classifier_is_generic_for_three_dynamic_options(tmp_path):
    router = _router(tmp_path, ["ALTERAR"])
    decision = await router.route(_state("quero mudar", ["CONFIRMAR", "ALTERAR", "CANCELAR"], "Escolha uma de {{ allowed_values }}"))
    assert decision.metadata["normalized_input"] == "ALTERAR"
    assert decision.metadata["allowed_values"] == ["CONFIRMAR", "ALTERAR", "CANCELAR"]


@pytest.mark.asyncio
async def test_semantic_classifier_reprompts_when_llm_returns_value_outside_allowlist(tmp_path):
    router = _router(tmp_path, ["TALVEZ"])
    decision = await router.route(_state("hmm", ["SIM", "NAO"], "Retorne uma de {{ allowed_values }}"))
    assert decision.mcp_tools == []
    assert decision.metadata["workflow_input_invalid"] is True
    assert decision.metadata["workflow_reprompt"] == "Escolha novamente."


def test_classifier_output_validator_uses_dynamic_allowlist():
    contract = {"allowed_values": ["A", "B", "C"], "normalize": "upper_strip"}
    assert match_semantic_classifier_output(" b ", contract) == "B"
    assert match_semantic_classifier_output("D", contract) is None


@pytest.mark.asyncio
async def test_semantic_classifier_receives_contiguous_relevant_context(tmp_path):
    router = _router(tmp_path, ["NAO"])
    history = [
        {"role": "user", "content": "qual é meu plano?", "metadata": {}},
        {"role": "assistant", "content": "Seu plano é X.", "metadata": {"intent": "contas_plan_query"}},
        {"role": "user", "content": "tem uma cobrança aqui que eu não reconheço", "metadata": {}},
        {"role": "assistant", "content": "Expliquei a fatura. Com essa explicação, sanei sua dúvida?", "metadata": {"intent": "owner_intent"}},
        {"role": "user", "content": "é a de quatorze e noventa e nove", "metadata": {}},
    ]
    prompt = (
        "Contexto:\
{{ relevant_conversation_context }}\
"
        "Atual={{ user_input }} Opções={{ allowed_values }}"
    )
    decision = await router.route(
        _state(
            "é a de quatorze e noventa e nove",
            ["SIM", "NAO"],
            prompt,
            history=history,
            include_relevant_context=True,
        )
    )
    assert decision.metadata["normalized_input"] == "NAO"
    context = decision.metadata["relevant_conversation_context"]
    assert "tem uma cobrança aqui que eu não reconheço" in context
    assert "Expliquei a fatura" in context
    assert "qual é meu plano?" not in context
    assert "Seu plano é X." not in context

    messages, kwargs = router.llm.calls[0]
    rendered = messages[0]["content"]
    assert "tem uma cobrança aqui que eu não reconheço" in rendered
    assert "é a de quatorze e noventa e nove" in rendered
    assert "max_tokens" not in kwargs


@pytest.mark.asyncio
async def test_semantic_classifier_context_does_not_inject_transaction_state(tmp_path):
    router = _router(tmp_path, ["NAO"])
    state = _state(
        "é a de quatorze e noventa e nove",
        ["SIM", "NAO"],
        "Contexto={{ relevant_conversation_context }}",
        history=[
            {"role": "user", "content": "tem uma cobrança que não reconheço", "metadata": {}},
            {"role": "assistant", "content": "Expliquei. Sanei sua dúvida?", "metadata": {"intent": "owner_intent"}},
            {"role": "user", "content": "é a de quatorze e noventa e nove", "metadata": {}},
        ],
        include_relevant_context=True,
    )
    state["active_transaction"] = {"tool": "contestar_cobranca", "subject": "x"}
    state["transaction_evidence"] = [{"secret": "should-not-be-in-context"}]
    decision = await router.route(state)
    context = decision.metadata["relevant_conversation_context"]
    assert "contestar_cobranca" not in context
    assert "should-not-be-in-context" not in context


@pytest.mark.asyncio
async def test_semantic_classifier_failure_exposes_raw_output_for_audit(tmp_path):
    router = _router(tmp_path, ["TALVEZ porque..."])
    decision = await router.route(
        _state("hmm", ["SIM", "NAO"], "Retorne {{ allowed_values }}")
    )
    assert decision.metadata["workflow_input_invalid"] is True
    assert decision.metadata["workflow_semantic_classifier"] is True
    assert decision.metadata["classifier_raw_output"] == "TALVEZ porque..."
    assert decision.metadata["allowed_values"] == ["SIM", "NAO"]

@pytest.mark.asyncio
async def test_context_anchor_excludes_older_same_intent_topic(tmp_path):
    router = _router(tmp_path, ["NAO"])
    state = _state(
        "é a de quatorze e noventa e nove",
        ["SIM", "NAO"],
        "Contexto={{ relevant_conversation_context }}",
        history=[
            {"role": "user", "content": "explique a fatura de janeiro", "metadata": {"message_id": "old-user"}},
            {"role": "assistant", "content": "Expliquei janeiro.", "metadata": {"intent": "owner_intent", "message_id": "old-assistant"}},
            {"role": "user", "content": "tem uma cobrança aqui que eu não reconheço", "metadata": {"message_id": "anchor-1"}},
            {"role": "assistant", "content": "Expliquei. Sanei sua dúvida?", "metadata": {"intent": "owner_intent", "message_id": "assistant-anchor"}},
            {"role": "user", "content": "é a de quatorze e noventa e nove", "metadata": {"message_id": "current"}},
        ],
        include_relevant_context=True,
    )
    state["pending_domain_workflow"]["context_anchor_message_id"] = "anchor-1"
    decision = await router.route(state)
    context = decision.metadata["relevant_conversation_context"]
    assert "tem uma cobrança aqui que eu não reconheço" in context
    assert "Expliquei. Sanei sua dúvida?" in context
    assert "explique a fatura de janeiro" not in context
    assert "Expliquei janeiro" not in context

@pytest.mark.asyncio
async def test_contextual_reentry_option_releases_pause_and_reroutes_with_bounded_context(tmp_path):
    routing = tmp_path / "routing.yaml"
    routing.write_text(
        """
router:
  fallback_agent: fallback_agent
  confidence_threshold: 0.70
intents:
  - name: invoice_explanation
    agent: billing_agent
    description: explanation
    domain: demo
    mcp_tools: [invoice_explanation]
  - name: contestation
    agent: contestation_agent
    description: contestation
    domain: demo
    mcp_tools: [consultar_faturas, contestar_cobranca]
""",
        encoding="utf-8",
    )
    llm = _ClassifierLLM([
        "CONTINUAR",
        '{"intent":"contestation","agent":"contestation_agent","confidence":0.99,"reason":"pedido anterior de não reconhecimento agora tem alvo identificado"}',
    ])
    settings = SimpleNamespace(
        ROUTING_CONFIG_PATH=str(routing),
        ENABLE_LLM_ROUTER=True,
        ENABLE_ROUTE_STICKINESS=False,
    )
    router = EnterpriseRouter(settings, llm=llm)
    state = _state(
        "é a de quatorze e noventa e nove",
        ["SIM", "NAO", "CONTINUAR"],
        "Classifique {{ user_input }} considerando {{ relevant_conversation_context }} em {{ allowed_values }}",
        history=[
            {"role": "user", "content": "tem uma cobrança aqui que eu não reconheço", "metadata": {"message_id": "anchor"}},
            {"role": "assistant", "content": "Tamboro Mensal R$ 14,99. Sanei sua dúvida?", "metadata": {"intent": "owner_intent"}},
            {"role": "user", "content": "é a de quatorze e noventa e nove", "metadata": {}},
        ],
        include_relevant_context=True,
    )
    state["pending_domain_workflow"]["context_anchor_message_id"] = "anchor"
    state["pending_domain_workflow"]["pause"]["expected_input"]["semantic_classifier"]["option_actions"] = {
        "CONTINUAR": {"action": "contextual_reentry"}
    }

    decision = await router.route(state)

    assert decision.intent == "contestation"
    assert decision.agent == "contestation_agent"
    assert decision.metadata["contextual_reentry"] is True
    assert decision.metadata["classifier_output"] == "CONTINUAR"
    assert decision.metadata["original_input"] == "é a de quatorze e noventa e nove"
    assert decision.metadata["user_claims_are_evidence"] is False
    effective = decision.metadata["contextual_reentry_input"]
    assert "tem uma cobrança aqui que eu não reconheço" in effective
    assert "Tamboro Mensal R$ 14,99" in effective
    assert "é a de quatorze e noventa e nove" in effective
    assert decision.mcp_tools == ["consultar_faturas", "contestar_cobranca"]


def test_invoice_explanation_uses_continue_as_contextual_reentry_option():
    import yaml
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    workflow = yaml.safe_load((root / "workflows" / "invoice_explanation.v2.yaml").read_text(encoding="utf-8"))
    formatar = next(node for node in workflow["nodes"] if node["id"] == "formatar")
    contract = formatar["pause"]["expected_input"]
    assert contract["allowed_values"] == ["SIM", "NAO", "CONTINUAR"]
    classifier = contract["semantic_classifier"]
    assert classifier["option_actions"]["CONTINUAR"]["action"] == "contextual_reentry"
    prompt = classifier["prompt"]
    assert "R$ 275,00" in prompt and "CONTINUAR" in prompt
    assert "quatorze e noventa e nove" in prompt and "CONTINUAR" in prompt
    assert "Nunca trate" in prompt
