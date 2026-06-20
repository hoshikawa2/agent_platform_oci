"""ToxRail — rail de detecção de toxicidade no input do cliente.

Mecanismo de baixa latência em dois passos:
  1. First-pass determinístico: blocklist de termos ofensivos óbvios em PT-BR
     via ``is_obvious_toxic`` de ``rules/tox_blocklist.py``. Retorno imediato,
     sem chamada LLM.
  2. LLM leve (20B) com prompt conciso para casos ambíguos — executa em paralelo
     com OOS/AOFERTA (via pipeline.py) para não adicionar latência sequencial.

Implementa o Protocol ``Rail`` de contracts.py.

Motivação de reativação (AT-05):
    TOX foi desativado por latência excessiva do mecanismo Nemo LLM original.
    O novo mecanismo resolve isso com: (a) blocklist determinística para casos
    óbvios, sem LLM; (b) LLM 20B leve (mesmo cliente de REVPREC/RAGSEC) com
    prompt conciso para casos ambíguos. Execução paralela com OOS/AOFERTA
    garante que o TOX não adicione latência sequencial ao pipeline.

Fallback conservador:
    Em caso de falha de parse ou erro do LLM, assume ``allowed=True`` (não
    bloqueia por falha técnica do guardrail).
"""
from __future__ import annotations

import json
import logging

from ..contracts import GuardRailContext, GuardRailLLMClient, RailDecision
from ..llm_adapter import AgentLLMClientAdapter
from ..rules.tox_blocklist import is_obvious_toxic

logger = logging.getLogger(__name__)

_FALLBACK_TEXT = (
    "Entendo que essa situação é frustrante. "
    "Posso te ajudar a verificar o que está acontecendo com sua conta."
)

_TOX_PROMPT_TEMPLATE = """\
# Guardrail de Toxicidade — Atendimento TIM

Você é um moderador de atendimento de telecomunicações. Analise se a mensagem \
abaixo contém toxicidade real (ofensas diretas, xingamentos pessoais, ameaças \
explícitas).

## Critérios de toxicidade (bloquear → allowed: false)
1. Xingamentos diretos ao atendente, à empresa ou a terceiros ("idiota", "lixo", "inútil").
2. Ameaças explícitas contra pessoas ("vou destruir", "vou matar", "vai se arrepender").
3. Discurso de ódio com intenção clara de ofender ou intimidar.

## NÃO é toxicidade (permitir → allowed: true)
- Frustração com o serviço ("que absurdo", "estou indignado", "não aguento mais").
- Reclamação enérgica sem ataque pessoal ("esse serviço é uma bagunça").
- Gírias ou informalidade sem ofensa ("mano, isso tá errado").
- Sarcasmo sobre a situação ("que surpresa, cobrou errado de novo").
- Urgência ou desespero genuíno ("preciso resolver AGORA").

## Exemplos

Texto: "Que absurdo! Vocês estão me cobrando errado há 3 meses!"
Saída: {{"allowed": true, "label": "NORMAL", "reason": "Reclamação legítima sem ofensa pessoal"}}

Texto: "Esse atendente é um idiota completo, não sabe nada!"
Saída: {{"allowed": false, "label": "TOXICO", "reason": "Xingamento direto ao atendente"}}

Texto: "Vou destruir vocês nas redes sociais e botar a Tim na justiça!"
Saída: {{"allowed": false, "label": "TOXICO", "reason": "Ameaça explícita de dano"}}

Texto: "Mano, já é a quarta vez que ligo sobre isso, tô de saco cheio"
Saída: {{"allowed": true, "label": "NORMAL", "reason": "Frustração informal, sem ofensa pessoal"}}

Texto: "Filho da puta, me passa meu dinheiro de volta"
Saída: {{"allowed": false, "label": "TOXICO", "reason": "Xingamento direto e explícito"}}

## Mensagem a analisar
{text}

## Saída obrigatória
Responda APENAS com JSON válido, sem texto adicional:
{{"allowed": true|false, "label": "TOXICO|NORMAL", "reason": "1 frase explicando"}}
"""


class ToxRail:
    """Rail de detecção de toxicidade no input do cliente (AT-05).

    Implementa o Protocol Rail. Executa first-pass determinístico via
    blocklist e, em caso de ambiguidade, delega ao LLM leve.

    Em caso de falha técnica (erro LLM, parse inválido), assume ``allowed=True``
    — não bloqueia o atendimento por falha do guardrail.
    """

    def __init__(self, llm_client: GuardRailLLMClient | None = None) -> None:
        """Inicializa o rail.

        Args:
            llm_client: instância que implementa GuardRailLLMClient Protocol.
                Quando None, instancia AgentLLMClientAdapter com configurações
                padrão do ambiente.
        """
        self._client: GuardRailLLMClient = llm_client or AgentLLMClientAdapter()

    @property
    def code(self) -> str:
        return "TOX"

    @property
    def fallback_text(self) -> str | None:
        from ..pipeline import _FALLBACK_BY_CODE
        return _FALLBACK_BY_CODE.get("TOX")

    @property
    def regen_flag(self) -> str | None:
        from ..prompts.fallback import _REGEN_FLAG_BY_CODE
        return _REGEN_FLAG_BY_CODE.get("TOX")

    @property
    def is_soft_alert(self) -> bool:
        return False

    def evaluate(self, context: GuardRailContext) -> RailDecision:
        """Avalia toxicidade no texto do usuário.

        Passo 1 — blocklist determinística: retorno imediato se óbvio.
        Passo 2 — LLM leve para casos ambíguos.

        Args:
            context: GuardRailContext com ``user_text`` contendo a mensagem
                do cliente a avaliar.

        Returns:
            RailDecision com ``allowed=False, code="TOX"`` quando toxicidade
            detectada; ``allowed=True`` caso contrário ou em falha técnica.
        """
        text = context.user_text

        # Passo 1: blocklist determinística — retorno imediato para casos óbvios
        if is_obvious_toxic(text):
            logger.warning(
                "tox_rail.blocklist_match session=%s text_prefix=%r",
                context.session_id,
                text[:80],
            )
            return RailDecision(
                allowed=False,
                code=self.code,
                reason="blocklist_match: toxicidade óbvia detectada sem LLM",
                fallback_text=_FALLBACK_TEXT,
            )

        # Passo 2: LLM para casos ambíguos
        prompt = _TOX_PROMPT_TEMPLATE.format(text=text)
        input_vars = {"text": text, "prompt": prompt, "context": {}}

        try:
            raw = self._client.invoke(self.code, input_vars)
            result: dict = json.loads(raw) if isinstance(raw, str) else raw
        except Exception as exc:
            logger.error(
                "tox_rail.invoke_error session=%s exc=%r — assuming allowed",
                context.session_id,
                exc,
            )
            # Fallback conservador: não bloqueia por falha técnica
            return RailDecision(
                allowed=True,
                code=self.code,
                reason="evaluation_error",
            )

        allowed = bool(result.get("allowed", True))
        reason = result.get("reason", "")
        label = result.get("label", "")

        if not allowed:
            logger.warning(
                "tox_rail.llm_blocked session=%s label=%r reason=%r",
                context.session_id,
                label,
                reason,
            )
            return RailDecision(
                allowed=False,
                code=self.code,
                reason=reason,
                fallback_text=_FALLBACK_TEXT,
            )

        return RailDecision(
            allowed=True,
            code=self.code,
            reason=reason,
        )


__all__ = ["ToxRail"]
