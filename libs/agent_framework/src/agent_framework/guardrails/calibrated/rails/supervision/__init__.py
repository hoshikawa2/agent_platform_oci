"""Rails de supervisão TIM — executados em nós específicos dos workflows.

Padrão de uso:
    results = evaluate_supervision_group([intencao_rail, correspondencia_rail], context)
    for decision in results:
        if not decision.allowed:
            # tratar violação
            ...

Os rails de supervisão diferem dos rails de pipeline (input/output) em três
aspectos:
1. São executados em nós específicos do grafo LangGraph, não no início/fim
   do turno.
2. Avaliam dados de transação estruturados (valor, itens, protocolos) além
   do texto da conversa.
3. São executados em paralelo entre si via ThreadPoolExecutor — cada rail
   é independente dos outros do mesmo grupo.

Falhas técnicas individuais (exceções) são capturadas e transformadas em
RailDecision com ``allowed=True`` e ``reason="evaluation_error"``. Esse
comportamento conservador garante que uma falha isolada não bloqueie o
atendimento — o monitoramento deve alertar para taxa de ``evaluation_error``
acima do esperado.

Rails implementados (AT-06.1 a AT-06.6):
    IntencaoCancelarRail        — pergunta investigativa tratada como cancelamento.
    CorrespondenciaItemRail     — item cancelado não corresponde ao reclamado.
    QuantidadeCoerente          — quantidade cancelada > quantidade mencionada.
    GroundednessRail            — resposta com dados não presentes no RAG/fatura.
    VerbalizacaoPrematura       — promessa antes de validação técnica.
    ServicoCorrretoRail         — VAS errado cancelado entre candidatos parecidos.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Sequence

from ...contracts import GuardRailContext, RailDecision, Rail
from .intencao_cancelar import IntencaoCancelarRail
from .correspondencia_item import CorrespondenciaItemRail
from .quantidade_coerente import QuantidadeCoerente
from .groundedness import GroundednessRail
from .verbalizacao_prematura import VerbalizacaoPrematura
from .servico_correto import ServicoCorrretoRail

logger = logging.getLogger(__name__)


def evaluate_supervision_group(
    rails: Sequence[Rail],
    context: GuardRailContext,
    *,
    max_workers: int | None = None,
) -> list[RailDecision]:
    """Executa uma lista de rails de supervisão em paralelo.

    Retorna lista de RailDecision ordenada: hard_blocks (is_soft_alert=False e
    allowed=False) primeiro, depois soft_alerts (is_soft_alert=True). Isso
    garante que o consumidor possa iterar pelos blocking decisions primeiro.

    Exceções individuais são capturadas e transformadas em RailDecision
    com allowed=True e reason="evaluation_error" (conservador — não bloqueia
    por falha técnica do guardrail).

    Soft-alerts (is_soft_alert=True) são logados via logger.warning antes
    de serem incluídos no retorno — o pipeline NÃO altera a resposta ao
    cliente nesses casos.

    Args:
        rails: sequência de objetos que implementam o Protocol ``Rail``.
            Cada rail é executado em thread separada.
        context: contexto de execução compartilhado por todos os rails.
        max_workers: número máximo de threads. Quando None, usa o padrão
            do ThreadPoolExecutor (min(32, cpu_count + 4)).

    Returns:
        Lista de RailDecision ordenada: hard_blocks primeiro, soft_alerts
        depois. Nunca lança exceção — falhas individuais viram RailDecision
        conservadores.
    """
    if not rails:
        return []

    raw_results: list[RailDecision | None] = [None] * len(rails)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {
            executor.submit(rail.evaluate, context): i
            for i, rail in enumerate(rails)
        }
        for future in as_completed(future_to_index):
            idx = future_to_index[future]
            rail = rails[idx]
            try:
                raw_results[idx] = future.result()
            except Exception as exc:
                logger.error(
                    "supervision_group.evaluation_error rail=%s session=%s exc=%r",
                    rail.code,
                    context.session_id,
                    exc,
                )
                raw_results[idx] = RailDecision(
                    allowed=True,
                    code=rail.code,
                    reason="evaluation_error",
                )

    # Garantia: nenhuma posição deve ser None após o loop.
    collected = [r for r in raw_results if r is not None]

    # Separar resultados em hard_blocks e soft_alerts
    hard_blocks: list[RailDecision] = []
    soft_alerts: list[RailDecision] = []

    for r in collected:
        if r.is_soft_alert:
            logger.warning(
                "supervision.soft_alert code=%s reason=%s",
                r.code,
                r.reason,
            )
            soft_alerts.append(r)
        else:
            hard_blocks.append(r)

    # Retornar hard_blocks primeiro, depois soft_alerts
    return hard_blocks + soft_alerts


__all__ = [
    "evaluate_supervision_group",
    "IntencaoCancelarRail",
    "CorrespondenciaItemRail",
    "QuantidadeCoerente",
    "GroundednessRail",
    "VerbalizacaoPrematura",
    "ServicoCorrretoRail",
]
