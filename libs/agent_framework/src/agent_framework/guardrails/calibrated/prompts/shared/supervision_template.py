"""Template padrão para prompts de rails de supervisão TIM.

Todos os 6 rails de supervisão (Intenção Cancelar, Correspondência Item,
Quantidade Coerente, Groundedness, Verbalização Prematura, Serviço Correto)
usam este template — variando apenas NOME, CRITÉRIOS e EXEMPLOS.
Modelo alvo: GPT-OSS-20B (tarefa binária estruturada com exemplos).
"""
from __future__ import annotations


def build_supervision_prompt(
    *,
    rail_name: str,
    criterios: str,
    historico: str,
    dados_transacao: str,
    exemplos: str,
) -> str:
    """Gera prompt padronizado para rail de supervisão.

    Args:
        rail_name: nome do guardrail (ex.: "Intenção Real de Cancelar").
        criterios: lista numerada de critérios de detecção (texto).
        historico: histórico da conversa formatado.
        dados_transacao: dados estruturados da transação (JSON ou texto).
        exemplos: 5-8 exemplos no formato "Input → Output JSON".

    Returns:
        String com o prompt completo pronto para envio ao LLM.
    """
    return f"""# Guardrail de Supervisão: {rail_name}
Você é um auditor especializado em atendimento de telecomunicações TIM.

## Tarefa
Detecte se a situação descrita constitui uma violação do guardrail "{rail_name}".
Analise o histórico e os dados da transação. Responda apenas com JSON válido.

## Critérios de Detecção
{criterios}

## Contexto da Conversa
HISTORICO:
{historico}

DADOS_TRANSACAO:
{dados_transacao}

## Exemplos Canônicos
{exemplos}

## Saída Obrigatória
Responda APENAS com JSON válido, sem texto adicional:
{{"violation": true|false, "confidence": "high|medium|low", "reason": "1 frase explicando a decisão"}}
"""


__all__ = ["build_supervision_prompt"]
