# Guardrails e judges externos: guia de implementação

Este guia mostra como criar políticas pertencentes ao agente sem acoplar regras de negócio ao `agent_framework`. Use uma extensão externa quando a regra tiver vocabulário, limites, evidências ou critérios próprios do domínio. Prefira os componentes nativos para controles genéricos já cobertos pelo framework.

## O que cada componente faz

| Componente | Momento | Contrato | Efeito |
|---|---|---|---|
| Guardrail | antes, durante ou depois da resposta | `evaluate(text, context)` | permite, sanitiza ou interrompe o fluxo |
| Judge | depois de existir uma resposta candidata | `evaluate(question, answer, context)` | mede qualidade; não reescreve a resposta |

Guardrails podem ser configurados nos estágios `input`, `retrieval`, `tool` e `output`. Judges são avaliações pós-resposta e podem ser amostrados, exceto quando `always_run_for_transactional` força a avaliação de transações.

## Estrutura recomendada no agente

```text
financial_agent/
  __init__.py
  extensions/
    __init__.py
    guardrails.py
    judges.py
config/
  guardrails.yaml
  judges.yaml
```

O pacote precisa estar importável no mesmo ambiente do backend. O caminho aceita `pacote.modulo:Classe` (recomendado) ou `pacote.modulo.Classe`.

## Implementar um guardrail

O método recebe o texto/argumentos serializados e um contexto do estágio. Ele deve sempre devolver `RailDecision`. Use `sanitized_text` somente quando a continuação com conteúdo alterado for segura.

```python external-guardrail-example
from __future__ import annotations

from typing import Any

from agent_framework.guardrails.base import Guardrail, RailDecision


class FinancialAmountRail(Guardrail):
    """Impede que uma ferramenta execute acima do limite do agente."""

    code = "FIN_AMOUNT"
    stage = "tool"

    def __init__(self, max_amount: float = 1500.0) -> None:
        self.max_amount = float(max_amount)

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        arguments = context.get("tool_args") or {}
        raw_amount = arguments.get("amount")
        if raw_amount is None:
            return RailDecision(code=self.code, allowed=False, reason="O argumento obrigatório 'amount' não foi informado.")
        try:
            amount = float(raw_amount)
        except (TypeError, ValueError):
            return RailDecision(code=self.code, allowed=False, reason="O argumento 'amount' deve ser numérico.")
        if amount > self.max_amount:
            return RailDecision(
                code=self.code,
                allowed=False,
                reason=f"Valor {amount:.2f} excede o limite {self.max_amount:.2f}.",
                metadata={"amount": amount, "max_amount": self.max_amount},
            )
        return RailDecision(code=self.code, allowed=True, metadata={"amount": amount, "max_amount": self.max_amount})
```

Declarações obrigatórias e seus motivos:

- herdar de `Guardrail` mantém o contrato público e facilita testes;
- `code` identifica decisão, telemetria e política; o YAML pode sobrescrevê-lo;
- `stage` documenta a intenção da classe, enquanto a seção do YAML determina onde ela roda;
- `evaluate(text, context)` deve aceitar exatamente esses argumentos;
- `allowed=False` nega a operação; a ação terminal é definida pela política no YAML;
- `reason` deve ser útil para diagnóstico, sem incluir segredo ou dado pessoal.

Métodos `async` rodam no event loop. Um `evaluate` síncrono também é aceito e roda em worker thread. Não faça I/O bloqueante dentro de um método `async`.

### Configurar o guardrail

```yaml external-guardrail-yaml
fail_fast: true
tool:
  - code: FIN_AMOUNT
    type: external
    class: financial_agent.extensions.guardrails:FinancialAmountRail
    enabled: true
    kwargs:
      max_amount: 1500.0
    policy:
      on_deny: handover
```

`type: external` ativa o import dinâmico; `class` aponta para a classe; `kwargs` vai para o construtor. `policy.on_deny` (ou o atalho `on_deny`) aceita `block`, `retry`, `handover`, `sanitize`, `observe` e `allow`. Ações terminais como `block`, `retry` e `handover` participam do `fail_fast`. Sanitizações são aplicadas na ordem estável do YAML.

O loader de guardrails não injeta `llm` nem `settings` no construtor. Quando um guardrail precisar do LLM compartilhado, leia `context["guardrail_llm"]` ou `context["llm"]`; esses valores só existem se o pipeline tiver sido criado com `GuardrailPipeline(llm=llm, ...)`. Trate ausência explicitamente.

## Implementar um judge

Um judge deve devolver `JudgeResult`. O construtor abaixo aceita todas as opções que o loader pode fornecer; `llm` e `settings` são injetados quando os parâmetros existem na assinatura.

```python external-judge-example
from __future__ import annotations

from typing import Any

from agent_framework.judges.judge import JudgeResult


class FinancialEvidenceJudge:
    name = "financial_evidence"

    def __init__(self, llm: Any | None = None, settings: Any | None = None,
                 threshold: float = 0.8, profile_name: str = "judge",
                 fail_closed: bool = True, max_context_chars: int = 12000,
                 fallback_on_block: bool = False) -> None:
        self.llm = llm
        self.settings = settings
        self.threshold = float(threshold)
        self.profile_name = profile_name
        self.fail_closed = bool(fail_closed)
        self.max_context_chars = int(max_context_chars)
        self.fallback_on_block = bool(fallback_on_block)

    def evaluate(self, question: str, answer: str, context: dict[str, Any]) -> JudgeResult:
        evidence = str(context.get("evidence") or "").strip()
        has_evidence = bool(evidence) and evidence.casefold() in answer.casefold()
        score = 1.0 if has_evidence else 0.0
        return JudgeResult(
            name=self.name,
            score=score,
            passed=score >= self.threshold,
            reason="Resposta contém a evidência financeira." if has_evidence else "Resposta sem evidência financeira verificável.",
            metadata={"threshold": self.threshold, "profile": self.profile_name},
        )
```

```yaml external-judge-yaml
enabled: true
sample_rate: 1.0
always_run_for_transactional: true
fail_closed: true
profile: judge
judges:
  - name: financial_evidence
    type: external
    class: financial_agent.extensions.judges:FinancialEvidenceJudge
    enabled: true
    threshold: 0.8
    kwargs: {}
```

O loader completa, se ausentes em `kwargs`, `threshold`, `profile_name`, `fail_closed`, `max_context_chars` e `fallback_on_block`, além de tentar injetar `llm` e `settings`. Não instancie outro provedor dentro da extensão: reutilize o cliente recebido para manter perfis, credenciais, telemetria e limites consistentes.

Judges síncronos rodam em worker threads; os assíncronos rodam no event loop. Todos são aguardados concorrentemente com resultado na ordem do YAML. O contexto entregue ao judge é compactado. Declare as chaves de evidência exigidas e não dependa de objetos grandes ou não serializáveis.

## Inicialização correta no backend

Os caminhos globais funcionam por argumento ou pelas configurações `GUARDRAILS_CONFIG_PATH` e `JUDGES_CONFIG_PATH`:

```python
guardrails = GuardrailPipeline(llm=llm, config_path="config/guardrails.yaml", fail_fast=True)
judges = JudgePipeline(llm=llm, settings=settings, config_path="config/judges.yaml")
```

### Limitação atual do `agent_template_backend`

O template corrente cria um único `GuardrailPipeline` e um único `JudgePipeline` no startup. Embora o registro de agentes possua `guardrails_config_path` e `judges_config_path`, apenas declarar caminhos diferentes em `agents.yaml` **não seleciona automaticamente pipelines por requisição**. Para isolamento multiagente real, a aplicação precisa manter pipelines em cache por perfil e escolher o par correto antes de executar o grafo. Até essa composição existir, trate os YAML carregados no startup como configuração global.

No template atual, o pipeline de guardrails também é criado sem `llm`, e o de judges sem `llm/settings`. Um guardrail externo determinístico funciona, mas extensões dependentes de LLM exigem alterar a composição conforme o exemplo acima. Sem isso, o judge externo pode receber `llm=None` e o guardrail não encontrará `context["guardrail_llm"]`.

## Falhas, segurança e observabilidade

- Guardrails convertem exceções em bloqueio quando `fail_closed=True`; em fail-open a decisão vira observação.
- Uma exceção de judge externo pode propagar pelo `asyncio.gather`; capture falhas esperadas dentro da extensão e devolva um `JudgeResult` coerente.
- Não registre prompt completo, credenciais, tokens, PII ou payload financeiro. Prefira `code`, duração, ação, score e correlação.
- Use fail-closed para autorização, segurança e transação. Fail-open só é adequado para métricas não críticas e deve gerar alerta.
- Mantenha códigos e nomes do domínio no pacote do agente. O core não deve importar `financial_agent`.

## Testar antes de publicar

Teste a classe e a integração do loader com o YAML. Este repositório transforma os blocos marcados acima em pacote temporário, importa as classes e executa ambos os pipelines:

```bash
pytest -q tests/test_external_guardrails_judges_documentation.py
```

Checklist: classe importável; assinatura e retorno corretos; `kwargs` validados no startup; allow/deny, limite, ausência e exceção cobertos; ação terminal e política de falha explícitas; `always_run_for_transactional` quando necessário; telemetria sem dados sensíveis; exemplo do manual aprovado no CI.

## Compatibilidade e migração

Uma política antiga deve migrar para o pacote do agente, não ser renomeada de forma cosmética dentro do core. Implementações genérica e específica podem coexistir; o YAML escolhe explicitamente o código/nome. Um shim temporário preserva imports antigos, mas código novo deve importar a implementação pertencente ao agente.
