from __future__ import annotations

import json
import os
from typing import Any

from .prompts.ausencia_oferta_proativa import build_aoferta_prompt
from .prompts.coerencia import build_coer_prompt
from .prompts._context import format_context_block
from .prompts.out_of_scope import build_oos_prompt
from .prompts.revprec import build_revprec_prompt
from .prompts.fraseologia import build_fraseologia_prompt
from .prompts.toxicidade_output import build_toxout_rewrite_prompt
from .prompts.tox import build_tox_prompt

# Segurança
from .prompts.dlex_in import build_dlex_in_prompt
from .prompts.dlex_out import build_dlex_out_prompt
from .prompts.pinj import build_pinj_prompt
from .prompts.ragsec import build_ragsec_prompt
from .prompts.fallback import build_fallback_prompt

_AOFERTA_TRIGGERS = (
    "quer aproveitar",
    "que tal tambem",
    "que tal também",
    "posso ja",
    "posso já",
    "ja que esta",
    "já que está",
    "aproveita e",
    "aproveite e",
    "tambem cancelar",
    "também cancelar",
)


# Mock determinístico do REVPREC: substrings de ação dada como FEITA (a pergunta do rail
# desde 2026-08-06). A detecção rica (fatura × ação, protocolo, histórico) é do prompt.
_REVPREC_MARKERS = (
    "cancelamento confirmado",
    "foi cancelado",
    "cancelado com sucesso",
    "cancelei",
    "cancelamos",
    "retiramos o valor",
    "retirei o valor",
    "contestacao foi registrada",
    "contestação foi registrada",
)


_TOXOUT_MOCK_PATTERNS = (
    r"\b(idiota|imbecil|burro|estúpido|inútil|maldito|miserável|incompetente)\b",
    r"\b(idiots?|stupid|useless|moron)\b",
)


_OOS_MOCK_TRIGGERS = (
    "política",
    "religião",
    "presidente",
    "concorrente",
    "vivo",
)


# Substrings inequívocas de fraseado proibido (mock determinístico). Mantidas
# curtas e sem ambiguidade para não colidir com falas legítimas; a detecção rica
# (allow-list, "entendo" no início etc.) é responsabilidade do prompt 20b real.
_FRASEOLOGIA_MOCK_TRIGGERS = (
    "bundle",
    "parceiro",
    "terceiros",
)


# Tasks cujo prompt pede UM DÍGITO (1 = passa, 0 = bloqueia) em vez de JSON, com o
# motivo do bloqueio fixado aqui. Gerar um `reason` por turno era o maior bloco de
# tokens de saída desses rails e nenhum consumidor o lia além do span.
_BINARY_TASKS: dict[str, str] = {
    "COER": "fala incompreensível ou negação ambígua na transcrição",
    "PINJ": "tentativa de prompt injection ou jailbreak detectada",
    "REVPREC": "agente afirmou cancelamento/retirada já executado, sem execução no turno",
}
# Polaridade do dígito de BLOQUEIO. Nos binários, 1 = passa e 0 = bloqueia; o REVPREC
# INVERTE porque a pergunta dele é positiva ("o agente disse que cancelou?"), e é essa
# forma que dá acurácia — 1 = achou a afirmação = bloqueia.
_BINARY_BLOCK_DIGIT: dict[str, str] = {"REVPREC": "1"}


class GuardrailLLMClient:
    """Roteador de prompts para os guardrails de supervisao provedor.

    Cliente síncrono de compatibilidade para os guardrails calibrados.

    O backend real é sempre o LLMProvider oficial do agent_framework, com os
    mesmos perfis/telemetria configurados na plataforma. Não cria gateway ou
    cliente LangChain paralelo.
    """

    # Todo guard ativo (AOFERTA, OOS, PINJ, FRASEOLOGIA) fixa 20b explicitamente
    # aqui — nenhum depende do default global (LLM_OCI_VARIANT), que segue
    # livre para a variante do orquestrador principal. PINJ usa 20b desde AT-15
    # (prompt expandido com 11 exemplos e 7 categorias torna a tarefa
    # suficientemente estruturada para modelo leve; antes da reescrita do
    # prompt em AT-03 usava 120b como compensação). FRASEOLOGIA: blocklist de
    # fraseado bem estruturada, mesma lógica. REVPREC (revprec_enabled=False
    # por default) não está listado — segue o default global até ser ativado.
    _TASK_OCI_VARIANT: dict[str, str] = {
        "AOFERTA": "20b",
        "OOS": "20b",
        "PINJ": "20b",
        "FRASEOLOGIA": "20b",
        "COER": "20b",
    }

    def __init__(self) -> None:
        # Mantido sem estado deliberadamente. O provider oficial resolve/cacheia
        # seus próprios clientes e perfis; esta camada não deve possuir outro pool.
        pass

    @property
    def use_mock(self) -> bool:
        return os.getenv("USE_MOCK_LLM", "true").lower() == "true"

    @staticmethod
    def _run_framework_classifier(task: str, payload: dict) -> dict:
        """Executa a API async oficial a partir desta facade síncrona.

        A aplicação nova usa GuardrailPipeline async diretamente. Esta bridge
        existe apenas para compatibilidade com rails calibrados legados já
        portados para o framework. Se houver event loop ativo, a coroutine é
        executada em thread isolada para evitar nested-loop/cross-event-loop.
        """
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        from agent_framework.guardrails.framework_llm_client import classify_with_framework_llm

        async def _call() -> dict:
            return await classify_with_framework_llm(None, task, payload)

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(_call())

        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="guardrail-compat") as executor:
            return executor.submit(lambda: asyncio.run(_call())).result()

    def classify(
        self,
        task: str,
        payload: dict,
        *,
        callbacks: list | None = None,
    ) -> dict:
        """Roteia uma task de guardrail para o LLM (ou mock).

        Contrato de retorno depende da task:
        - PINJ / COER: {"allowed", "label", "reason"} — o PROMPT devolve só um
          dígito (1 = passa, 0 = bloqueia) e a conversão mora em `_BINARY_TASKS`;
          o `reason` é fixo. Nenhum consumidor de produção lia o `label` desses
          rails, e gerar `reason` por turno era a maior parcela da latência
          (PINJ: 1115 ms -> 476 ms com a saída binária, medido em 2026-08-05).
        - AOFERTA / OOS: {"allowed", "reason"} (JSON do prompt; `label` saiu de
          ambos — nenhum consumidor o lia, só gastava token). Por contrato do
          prompt o `reason` vem VAZIO quando allowed=true, como no FRASEOLOGIA.
        - REVPREC: {"allowed", "label", "reason"} — binário como PINJ/COER, mas com
          polaridade INVERTIDA (`_BINARY_BLOCK_DIGIT`): a pergunta é "o agente disse que
          cancelou?", então `1` bloqueia. Reescrito em 2026-08-06; a forma anterior
          (JSON de 4 campos, algoritmo de 9 passos) julgava promessa FUTURA e dava OK
          ao pretérito — deixava passar exatamente a fala que interessa.
        - TOXOUT: {"text": str} — texto reescrito sem trechos toxicos.

        `callbacks` (opcional) eh repassado via `config={"callbacks": ...}`
        para `llm.invoke`. Permite que o caller (ex.: loop._finalize_run)
        injete o `LangfuseCallbackHandler` para que o `ChatLLM` da reescrita
        apareca como span no Langfuse.
        """
        if self.use_mock:
            return self._mock_classify(task, payload)

        # O caminho real usa exclusivamente o provider oficial do framework.
        # O helper async preserva perfis (guardrail/grl), telemetria Langfuse e
        # parsing binário/JSON calibrado.
        return self._run_framework_classifier(task, payload)

    def _mock_classify(self, task: str, payload: dict) -> dict:
        # Reutiliza o mesmo fallback determinístico e explicável do pipeline
        # moderno do framework, evitando divergência entre paths sync/async.
        from agent_framework.guardrails.framework_llm_client import _mock_classify
        return _mock_classify(task, payload)
