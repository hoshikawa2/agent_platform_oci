from agent_framework.guardrails.calibrated.prompts.fraseologia import build_fraseologia_prompt


def test_fraseologia_prompt_allows_business_parameter_collection():
    prompt = build_fraseologia_prompt("[ContestacaoAgent] Para prosseguir, informe valor.")
    assert '"Para prosseguir, informe valor."' in prompt
    assert "DADOS DE NEGOCIO" in prompt
    assert "NAO expoe raciocinio" in prompt


def test_fraseologia_prompt_distinguishes_business_data_from_internal_keys():
    prompt = build_fraseologia_prompt("Informe subject.")
    assert '"subject"' in prompt
    assert '"asset_id"' in prompt
    assert '"invoice_id"' in prompt
    assert '"COLLECTING_PARAMETERS"' in prompt
    assert '"AWAITING_CONFIRMATION"' in prompt


def test_fraseologia_prompt_keeps_natural_transaction_confirmation_allowed():
    prompt = build_fraseologia_prompt("Voce confirma o cancelamento do servico TIM Fashion?")
    assert "confirmacoes de uma acao ja em andamento" in prompt
    assert "TIM Fashion" in prompt
