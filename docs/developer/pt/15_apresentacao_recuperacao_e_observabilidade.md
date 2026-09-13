### Apresentação, recuperação e observabilidade

### Renderers de resposta

Quando uma tool retorna dados estruturados confiáveis, `response.mode: renderer` produz uma resposta determinística e evita que o LLM altere valores, protocolos ou status.

```yaml
tools:
  consultar_saldo:
    description: Consulta saldo da conta.
    mcp_server: financial
    enabled: true
    response:
      mode: renderer
      renderer: financial.balance
```

```python renderer-example
from typing import Any

from agent_framework.presentation import register_tool_response_renderer


def render_balance(*, tool_name: str, result: dict[str, Any],
                   state: dict[str, Any], agent_label: str) -> str | None:
    account = result.get("account_masked")
    balance = result.get("balance")
    currency = result.get("currency", "BRL")
    if account is None or balance is None:
        return None
    return f"[{agent_label}] Conta {account}: saldo {currency} {float(balance):.2f}."


def register_financial_renderers() -> None:
    register_tool_response_renderer("financial.balance", render_balance)
```

Importe e execute `register_financial_renderers()` uma vez no startup. A assinatura é keyword-only e deve aceitar `tool_name`, `result`, `state` e `agent_label`. Retorne `None` quando faltarem campos obrigatórios para permitir o fallback previsto pelo runtime. Nunca interpolar o payload inteiro: selecione campos permitidos, mascare identidade e formate valores explicitamente.

### Organização de `app/presentation/`

No `agent_template_backend`, renderers específicos do domínio ficam em:

```text
app/presentation/
├── __init__.py
└── tool_renderers.py
```

A pasta existe para separar **como um resultado confiável do domínio deve ser apresentado** da infraestrutura genérica que seleciona e executa renderers. Assim:

- `app/presentation/` implementa funções como `financial.balance`, `billing.invoice` ou outro renderer específico do agente;
- `agent_framework.presentation` mantém registry, contrato de chamada e mecanismo genérico de integração com o runtime;
- `config/tools.yaml` seleciona `response.mode: renderer` e o nome do renderer;
- o startup do agente importa/registra os renderers uma única vez.

Renderers não devem buscar dados, decidir autorização, executar tools, alterar estado transacional ou reinterpretar um resultado usando LLM. A entrada já deve representar um resultado autorizado/confiável; o renderer apenas seleciona, mascara e formata campos.

**Anti-padrão:** criar em `app/presentation/` uma cópia do registry ou do pipeline de apresentação do framework. Se vários agentes precisarem do mesmo mecanismo de formatação/seleção, ele deve evoluir no core; somente a apresentação específica do domínio fica no agente.

### Output Supervisor

O Output Supervisor valida a resposta candidata antes da saída final. Ele pode permitir, sanitizar, solicitar retry, bloquear, entregar a humano ou observar. `OUTPUT_SUPERVISOR_MAX_RETRIES` deve ter limite pequeno; cada retry precisa de orientação objetiva e a resposta reescrita deve passar novamente pelos controles. Não use retry para erro permanente de autorização ou indisponibilidade.

### Recuperação de workflow

Classifique falhas em: validação, dependência temporária, dependência permanente, persistência e erro de programação. O usuário recebe mensagem segura; a telemetria recebe classe, fase, tentativa, workflow/version/execution ID e correlação. Para efeitos externos:

- antes do envio, um retry controlado é aceitável;
- depois de envio com resultado incerto, consulte status/idempotência;
- após confirmação externa, persista o resultado antes de responder;
- uma nova mensagem do usuário não deve apagar evidência de uma execução incerta.

Checkpoints resilientes podem repetir operações de armazenamento, validar integridade, compactar histórico e recuperar o último checkpoint válido. Isso não torna automaticamente uma action externa idempotente.

### Interrupção de voz e replay

No barge-in, preserve o texto confirmado, marque a resposta interrompida e não reapresente áudio obsoleto. O replay deve usar identificadores de interação/mensagem e a mesma sessão escopada. Se uma transação estava pendente, a fala interrompida não conta como confirmação. Ao retomar, revalide estado, confirmação e idempotência.

### Eventos IC, NOC e GRL

- IC: comportamento funcional, decisão, tool, cache e workflow;
- NOC: disponibilidade, timeout, dependência e latência operacional;
- GRL: decisão e ação de guardrail/supervisor.

Use o `AgentObserver`/adapter do template em vez de chamar diretamente um backend de telemetria. Inclua `tenant_id`, `agent_id`, `session_id`, `transaction_id`/`execution_id`, componente e duração quando disponíveis. Nunca inclua credenciais, prompt integral, PII ou payload financeiro bruto.

### Mapeamento e compatibilidade

Quando consumidores históricos exigirem códigos diferentes, use um registry/overlay como `observability_mapping.yaml`: evento semântico interno → label externo. O default é compartilhado e o overlay pertence ao agente. Não hardcode labels históricas no executor nem renomeie o evento interno de forma que perca semântica.

### Pub/Sub e sequência

Publicação deve ocorrer após a decisão funcional e não pode alterar seu resultado. Configure provider, tópicos/streams, filtros e política de falha. Quando o consumidor exigir ordem, publique `sequence`, chave de partição estável e correlação; múltiplos pods não garantem ordem global. Defina TTL/retenção e comportamento para duplicatas. Eventos filtrados no Pub/Sub continuam disponíveis nos outros destinos de observabilidade.

### Checklist operacional

- renderer não expõe payload bruto;
- resposta sanitizada é revalidada;
- retries têm limite e distinguem erro transitório;
- efeitos incertos consultam idempotência/status;
- evento contém correlação e não contém segredo;
- labels externas são mapeadas por configuração;
- sequência e chave de partição são testadas com múltiplos consumidores;
- interrupção de voz não confirma nem repete transação.

O exemplo de renderer é compilado e executado por `tests/test_advanced_developer_documentation.py`.

