# Planejamento Multi-Intent

O `MultiIntentPlanner` reconhece solicitações independentes na mesma mensagem e
cria um plano limitado às intents, agents e tools declarados em
`config/routing.yaml`. O planejador não executa operações nem permite que o LLM
invente uma sequência: o roteador escolhe a operação primária e o workflow do
domínio continua responsável pela transação.

## Configuração

Não existe configuração adicional. O planejador usa as intents do `routing.yaml`
e lê `tool_policies.yaml` para priorizar automaticamente a única operação
transacional. Pedidos secundários são persistidos em `pending_topics`.

- intent conhecida e read-only: executada pelo agent correspondente;
- intent conhecida e transacional: mantida pendente para confirmação própria;
- trecho sem capability correspondente: respondido como `off_context`.

Consultas secundárias com `execute` podem ser executadas pelo agent correspondente
e consolidadas. Uma segunda mutação é marcada como `defer`, pois exige um
workflow transacional coordenador.

## Fluxo de execução

1. O `EnterpriseRouter` separa a entrada em cláusulas e resolve cada uma pelas
   keywords das intents cadastradas.
2. `tool_policies.yaml` identifica a operação transacional e a torna primária.
3. A primeira operação é roteada normalmente para seu agent/workflow.
4. O `agent_graph` compõe as mensagens públicas antes do supervisor de saída.
5. Durante uma confirmação, uma frase como `sim e me manda a segunda via`
   confirma a transação aberta e registra a solicitação secundária, sem causar
   troca indevida de intent.

## Operações mutáveis

Para executar mais de uma ação com efeito colateral, implemente um workflow
transacional coordenador. Ele deve persistir o plano, pedir confirmação quando
necessário, executar cada passo com idempotência e registrar sucesso parcial,
falha e compensação. O planejador fornece o contrato; a política de negócio e a
orquestração permanecem no domínio.

## Referência executável

Veja os testes genéricos em `tests/unit/test_multi_intent_planner.py`. Como a
feature é padrão do runtime, não existe uma cópia especial do
`agent_template_backend` em `Tuning-Performance`.
