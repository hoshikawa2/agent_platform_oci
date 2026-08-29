import pytest

from agent_framework.guardrails.rails import DataLeakageOutputRail


@pytest.mark.asyncio
async def test_dlex_out_masks_protocol_explicitly_authorized_by_expected_protocols(monkeypatch):
    captured = {}

    async def fake_classifier(_llm, task, payload, **_kwargs):
        assert task == "DLEX_OUT"
        captured.update(payload)
        assert "1234567890" not in payload["text"]
        assert "<AUTHORIZED_PROTOCOL>" in payload["text"]
        # The raw value must also not leak back into classifier context.
        assert "1234567890" not in repr(payload["context"])
        return {"allowed": True, "label": "OK", "reason": "authorized protocol masked"}

    monkeypatch.setattr(
        "agent_framework.guardrails.rails.classify_with_framework_llm", fake_classifier
    )

    rail = DataLeakageOutputRail()
    decision = await rail.evaluate(
        "Seu número de protocolo é 1234567890.",
        {
            "__guardrails_yaml_controlled": True,
            "expected_protocols": ["1234567890"],
        },
    )

    assert decision.allowed is True
    assert decision.sanitized_text == "Seu número de protocolo é 1234567890."
    assert decision.metadata["protocol_authorization"] == "expected_values"
    assert decision.metadata["authorized_protocols_masked"] == 1


@pytest.mark.asyncio
async def test_dlex_out_does_not_mask_unexpected_protocol(monkeypatch):
    async def fake_classifier(_llm, task, payload, **_kwargs):
        assert task == "DLEX_OUT"
        assert "9999999999" in payload["text"]
        assert "<AUTHORIZED_PROTOCOL>" not in payload["text"]
        return {"allowed": False, "label": "DLEX_OUT", "reason": "unexpected identifier"}

    monkeypatch.setattr(
        "agent_framework.guardrails.rails.classify_with_framework_llm", fake_classifier
    )

    rail = DataLeakageOutputRail()
    decision = await rail.evaluate(
        "Seu número de protocolo é 9999999999.",
        {
            "__guardrails_yaml_controlled": True,
            "expected_protocols": ["1234567890"],
        },
    )

    assert decision.allowed is False
    assert "protocol_authorization" not in decision.metadata


@pytest.mark.asyncio
async def test_dlex_out_masks_expected_protocol_but_keeps_other_sensitive_content_visible(monkeypatch):
    async def fake_classifier(_llm, task, payload, **_kwargs):
        assert task == "DLEX_OUT"
        assert "1234567890" not in payload["text"]
        assert "<AUTHORIZED_PROTOCOL>" in payload["text"]
        assert "sk-abcdefghijklmnop" in payload["text"]
        return {"allowed": False, "label": "DLEX_OUT", "reason": "secret remains visible"}

    monkeypatch.setattr(
        "agent_framework.guardrails.rails.classify_with_framework_llm", fake_classifier
    )

    rail = DataLeakageOutputRail()
    decision = await rail.evaluate(
        "Protocolo 1234567890; token sk-abcdefghijklmnop",
        {
            "__guardrails_yaml_controlled": True,
            "expected_protocols": ["1234567890"],
        },
    )

    assert decision.allowed is False
    assert decision.metadata["protocol_authorization"] == "expected_values"

@pytest.mark.asyncio
async def test_dlex_out_rechecks_and_allows_false_positive_caused_only_by_authorized_protocol(monkeypatch):
    calls = []

    async def fake_classifier(_llm, task, payload, **_kwargs):
        assert task == "DLEX_OUT"
        calls.append(payload)
        if len(calls) == 1:
            assert "<AUTHORIZED_PROTOCOL>" in payload["text"]
            return {
                "allowed": False,
                "label": "DLEX_OUT",
                "reason": "Resposta expõe protocolo interno (identificador) que não é permitido divulgar",
            }
        assert "1234567890" not in payload["text"]
        assert "referência pública autorizada para este cliente" in payload["text"]
        assert payload["context"]["authorized_customer_protocol"] is True
        return {"allowed": True, "label": "OK", "reason": "nenhum outro vazamento"}

    monkeypatch.setattr(
        "agent_framework.guardrails.rails.classify_with_framework_llm", fake_classifier
    )

    rail = DataLeakageOutputRail()
    decision = await rail.evaluate(
        "A contestação foi criada com sucesso. O protocolo gerado é 1234567890.",
        {
            "__guardrails_yaml_controlled": True,
            "expected_protocols": ["1234567890"],
        },
    )

    assert decision.allowed is True
    assert len(calls) == 2
    assert decision.metadata["protocol_authorization"] == "expected_values"
    assert decision.metadata["protocol_authorization_verified"] is True


@pytest.mark.asyncio
async def test_dlex_out_recheck_does_not_hide_other_leakage(monkeypatch):
    calls = []

    async def fake_classifier(_llm, task, payload, **_kwargs):
        assert task == "DLEX_OUT"
        calls.append(payload)
        # First pass blocks; second pass must still see the unrelated secret.
        assert "sk-abcdefghijklmnop" in payload["text"]
        return {"allowed": False, "label": "DLEX_OUT", "reason": "token secreto exposto"}

    monkeypatch.setattr(
        "agent_framework.guardrails.rails.classify_with_framework_llm", fake_classifier
    )

    rail = DataLeakageOutputRail()
    decision = await rail.evaluate(
        "Protocolo 1234567890; token sk-abcdefghijklmnop",
        {
            "__guardrails_yaml_controlled": True,
            "expected_protocols": ["1234567890"],
        },
    )

    assert decision.allowed is False
    assert len(calls) == 1
    assert decision.metadata["protocol_authorization"] == "expected_values"
    assert decision.metadata["protocol_authorization_verified"] is False
