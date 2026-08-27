import pytest

from agent_framework.guardrails.rails import ComplianceRail


@pytest.mark.asyncio
async def test_cmp_accepts_expected_protocol_directly_even_when_regex_misses_markdown_distance():
    rail = ComplianceRail()
    text = (
        "[FaturasAgent] Entendido. Seu aceite foi registrado e o protocolo de atendimento "
        "foi aberto com o número **1234567890**."
    )

    decision = await rail.evaluate(
        text,
        {
            "tipo_fluxo": "ajuste",
            "expected_protocols": ["1234567890"],
        },
    )

    assert decision.allowed is True
    assert decision.sanitized_text is None
    assert decision.metadata["protocol_validation"] == "expected_values"
    assert decision.metadata["expected_protocols"] == ["1234567890"]


@pytest.mark.asyncio
async def test_cmp_does_not_accept_a_different_protocol_when_expected_value_is_known():
    rail = ComplianceRail()
    text = "Seu protocolo é 9999999999."

    decision = await rail.evaluate(
        text,
        {
            "requer_protocolo": True,
            "expected_protocols": ["1234567890"],
        },
    )

    assert decision.allowed is True
    assert decision.sanitized_text is not None
    assert "um dois três quatro cinco seis sete oito nove zero" in decision.sanitized_text
    assert decision.metadata["missing_protocols_spoken"] == [
        "um dois três quatro cinco seis sete oito nove zero"
    ]
    assert decision.metadata["protocol_validation"] == "expected_values"


@pytest.mark.asyncio
async def test_cmp_keeps_regex_compatibility_when_expected_protocols_are_unavailable():
    rail = ComplianceRail()

    decision = await rail.evaluate(
        "Seu protocolo é 1234567890.",
        {"requer_protocolo": True},
    )

    assert decision.allowed is True
    assert decision.metadata["protocol_validation"] == "generic_regex"
