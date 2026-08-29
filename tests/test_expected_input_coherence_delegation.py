import pytest

from agent_framework.guardrails.rails import CoherenceRail


@pytest.mark.asyncio
async def test_coer_delegates_to_enumerated_expected_input_contract_without_calling_llm():
    rail = CoherenceRail()
    decision = await rail.evaluate(
        "ano",
        {
            "expected_input": {
                "key": "resposta_usuario",
                "allowed_values": ["SIM", "NAO"],
                "normalize": "upper_strip",
                "reprompt": "Não entendi. Responda sim ou não.",
            }
        },
    )
    assert decision.allowed is True
    assert decision.code == "COER"
    assert decision.metadata["mechanism"] == "expected_input_contract"
    assert decision.metadata["delegated"] is True


@pytest.mark.asyncio
async def test_coer_without_expected_input_keeps_normal_classification(monkeypatch):
    async def fake_classifier(*args, **kwargs):
        return {"allowed": False, "label": "COER", "reason": "fala incompreensível"}

    monkeypatch.setattr("agent_framework.guardrails.rails.classify_with_framework_llm", fake_classifier)
    rail = CoherenceRail()
    decision = await rail.evaluate("ano", {})
    assert decision.allowed is False
    assert decision.metadata["mechanism"] == "llm_rail"


@pytest.mark.asyncio
async def test_coer_emits_non_blocking_semantic_signal_for_opt_in_unmatched(monkeypatch):
    async def fake_classifier(*args, **kwargs):
        return {"allowed": True, "label": "OK", "reason": "fala coerente e substantiva"}

    monkeypatch.setattr("agent_framework.guardrails.rails.classify_with_framework_llm", fake_classifier)
    rail = CoherenceRail()
    decision = await rail.evaluate(
        "então tirando esses serviços o valor será 275, certo?",
        {
            "expected_input": {
                "key": "resposta_usuario",
                "allowed_values": ["SIM", "NAO"],
                "normalize": "upper_strip",
                "reprompt": "Não entendi. Responda sim ou não.",
                "unmatched": {
                    "meaningful_input": {"action": "resume_as", "value": "NAO"}
                },
            }
        },
    )
    assert decision.allowed is True
    assert decision.metadata["mechanism"] == "expected_input_contract"
    assert decision.metadata["semantic_coherent"] is True
    assert decision.metadata["data"]["allowed"] is True


@pytest.mark.asyncio
async def test_coer_emits_incoherent_signal_without_blocking_when_unmatched_policy_exists(monkeypatch):
    async def fake_classifier(*args, **kwargs):
        return {"allowed": False, "label": "COER", "reason": "fala incompreensível"}

    monkeypatch.setattr("agent_framework.guardrails.rails.classify_with_framework_llm", fake_classifier)
    rail = CoherenceRail()
    decision = await rail.evaluate(
        "ano",
        {
            "expected_input": {
                "key": "resposta_usuario",
                "allowed_values": ["SIM", "NAO"],
                "normalize": "upper_strip",
                "reprompt": "Não entendi. Responda sim ou não.",
                "unmatched": {
                    "meaningful_input": {"action": "resume_as", "value": "NAO"}
                },
            }
        },
    )
    assert decision.allowed is True
    assert decision.metadata["semantic_coherent"] is False


@pytest.mark.asyncio
async def test_coer_delegates_without_own_llm_when_semantic_classifier_is_configured(monkeypatch):
    async def should_not_run(*args, **kwargs):
        raise AssertionError("COER LLM should not run when expected_input semantic_classifier owns semantics")

    monkeypatch.setattr("agent_framework.guardrails.rails.classify_with_framework_llm", should_not_run)
    rail = CoherenceRail()
    decision = await rail.evaluate(
        "legal!",
        {
            "expected_input": {
                "key": "resposta_usuario",
                "allowed_values": ["SIM", "NAO"],
                "normalize": "upper_strip",
                "semantic_classifier": {
                    "enabled": True,
                    "prompt": "Classifique em {{ allowed_values }}",
                },
            }
        },
    )
    assert decision.allowed is True
    assert decision.metadata["mechanism"] == "expected_input_semantic_classifier"
    assert decision.metadata["delegated"] is True

@pytest.mark.asyncio
async def test_coer_delegates_short_reply_to_active_transaction_parameter_contract(monkeypatch):
    async def should_not_run(*args, **kwargs):
        raise AssertionError("COER LLM must not own coherence while transaction parameters are being collected")

    monkeypatch.setattr("agent_framework.guardrails.rails.classify_with_framework_llm", should_not_run)
    rail = CoherenceRail()
    decision = await rail.evaluate(
        "Tamboro",
        {
            "transaction_status": "COLLECTING_PARAMETERS",
            "missing_parameters": ["subject"],
            "active_transaction": {"tool_name": "contestar_cobranca"},
        },
    )
    assert decision.allowed is True
    assert decision.metadata["mechanism"] == "transaction_parameter_contract"
    assert decision.metadata["delegated"] is True
    assert decision.metadata["missing_parameters"] == ["subject"]
