### Manual de Implementação — Long-Term Memory

### Conceito

A Long-Term Memory (LTM) é a capacidade do `agent_framework` de armazenar e recuperar fatos duradouros além da duração de uma sessão de conversa.

Diferentemente do histórico de mensagens, que normalmente está associado a um `session_id`, a memória de longo prazo é associada à identidade de negócio do usuário ou cliente. Na implementação atual, essa identidade é composta por:

```text
tenant_id
agent_id
customer_key
```

Isso permite que um agente recupere preferências, informações de identidade, projetos e restrições mesmo quando uma nova sessão é criada.

### Para que serve

A Long-Term Memory serve para:

- manter continuidade entre sessões;
- personalizar respostas;
- evitar que o usuário repita informações já fornecidas;
- reduzir a necessidade de enviar todo o histórico ao modelo;
- armazenar preferências, projetos atuais, nomes preferidos e restrições;
- isolar a memória entre tenants, agentes e clientes.

Exemplo:

```text
Sessão A:
"Me chame de Cris. Minha linguagem preferida é Python."

Sessão B, com outro session_id e o mesmo customer_key:
"O que você lembra sobre mim?"

Resposta esperada:
"Seu nome preferido é Cris e sua linguagem preferida é Python."
```

### Diferença entre os tipos de memória

#### Conversation Memory

Mantém as mensagens da conversa atual e normalmente está associada ao `session_id`.

#### Summary Memory

Mantém um resumo da conversa para reduzir o tamanho do contexto enviado ao modelo.

#### Long-Term Memory

Mantém fatos duradouros entre sessões e é associada à identidade de negócio, principalmente ao `customer_key`.

### Componentes da funcionalidade

#### LongTermMemoryManager

Responsável por coordenar:

- carregamento das memórias;
- recuperação por identidade;
- renderização do contexto;
- extração de novos fatos;
- persistência dos fatos;
- deduplicação e atualização.

#### LongTermMemoryStore

Interface de persistência utilizada pelo manager.

#### SQLiteLongTermMemoryStore

Implementação de referência baseada em SQLite.

É apropriada para:

- desenvolvimento local;
- testes;
- demonstrações;
- ambientes de baixa escala.

#### InMemoryLongTermMemoryStore

Implementação em memória utilizada para testes rápidos.

O conteúdo é perdido quando o processo do backend é encerrado.

#### LongTermMemoryExtractor

Responsável por identificar fatos duradouros nas mensagens.

Exemplos de fatos:

```text
preferred_name = Cris
preferred_language = Python
current_project = Atlas
```

#### LongTermMemoryItem

Modelo que representa um item persistido, incluindo identidade, chave, valor, categoria, confiança e metadados.

#### AgentRuntime

Carrega a memória antes da execução do agente e injeta o contexto no prompt.

#### Nó persist_long_term_memory

Nó do LangGraph responsável por persistir os fatos após a geração e validação da resposta final.

### Estrutura dos arquivos

```text
libs/
└── agent_framework/
    └── src/
        └── agent_framework/
            └── memory/
                ├── __init__.py
                ├── long_term_extractor.py
                ├── long_term_memory.py
                ├── long_term_models.py
                └── long_term_store.py
```

### Fluxo de execução

```text
Mensagem do usuário
        │
        ▼
AgentRuntime.prepare_memory_context()
        │
        ├── Conversation Memory
        ├── Summary Memory
        └── Long-Term Memory
                    │
                    ▼
          long_term_memory_context
                    │
                    ▼
             Prompt do agente
                    │
                    ▼
                 Agente
                    │
                    ▼
       Guardrails / Judges / Supervisor
                    │
                    ▼
       persist_long_term_memory
                    │
                    ▼
          LongTermMemoryExtractor
                    │
                    ▼
           LongTermMemoryStore
```

### Configuração do framework

### Novos módulos

Copie os arquivos:

```text
libs/agent_framework/src/agent_framework/memory/long_term_extractor.py
libs/agent_framework/src/agent_framework/memory/long_term_memory.py
libs/agent_framework/src/agent_framework/memory/long_term_models.py
libs/agent_framework/src/agent_framework/memory/long_term_store.py
```

### Atualização de memory/__init__.py

Exporte os componentes da Long-Term Memory:

```python
from agent_framework.memory.long_term_memory import (
    LongTermMemoryManager,
    create_long_term_memory_manager,
)
from agent_framework.memory.long_term_models import LongTermMemoryItem
from agent_framework.memory.long_term_store import (
    InMemoryLongTermMemoryStore,
    LongTermMemoryStore,
    SQLiteLongTermMemoryStore,
    create_long_term_memory_store,
)
```

### Atualização de settings.py

Adicione as configurações:

```python
ENABLE_LONG_TERM_MEMORY: bool = False
LONG_TERM_MEMORY_PROVIDER: str = "sqlite"
LONG_TERM_MEMORY_SQLITE_PATH: str = "./data/agent_framework.db"
LONG_TERM_MEMORY_TABLE: str = "agentfw_long_term_memory"
LONG_TERM_MEMORY_MAX_CONTEXT_ITEMS: int = 20
LONG_TERM_MEMORY_MIN_CONFIDENCE: float = 0.70
LONG_TERM_MEMORY_AUTO_EXTRACT: bool = True
LONG_TERM_MEMORY_INJECT_CONTEXT: bool = True
```

### Integração com AgentRuntime

O runtime deve:

1. verificar se a funcionalidade está habilitada;
2. criar o manager quando necessário;
3. recuperar os fatos pela identidade;
4. preencher o estado;
5. injetar o contexto no prompt.

Campos adicionados ao estado:

```python
long_term_memories: list[dict]
long_term_memory_context: str
long_term_memory_write_result: dict
```

### Inicialização no AgentWorkflow

O manager deve ser criado no `AgentWorkflow`:

```python
self.long_term_memory_manager = create_long_term_memory_manager(
    settings,
    telemetry=telemetry,
)
```

### Inicialização correta dos agentes

O `long_term_memory_manager` não deve ser passado pelo `agent_kwargs` caso os construtores de `BillingAgent`, `ProductAgent`, `OrdersAgent` e `SupportAgent` não declarem esse parâmetro.

Esta inicialização causa erro:

```python
agent_kwargs = {
    "telemetry": telemetry,
    "settings": settings,
    "memory": memory,
    "summary_memory": summary_memory,
    "long_term_memory_manager": self.long_term_memory_manager,
}

self.billing = BillingAgent(llm, **agent_kwargs)
```

Erro resultante:

```text
TypeError: BillingAgent.__init__() got an unexpected keyword argument
'long_term_memory_manager'
```

A forma recomendada é criar os agentes com a assinatura já existente e injetar o manager como atributo após a inicialização:

```python
agent_kwargs = {
    "telemetry": telemetry,
    "tool_router": getattr(self, "tool_router", None),
    "rag_service": self.rag_service,
    "cache": self.cache,
    "settings": settings,
    "observer": self.observer,
    "memory": memory,
    "summary_memory": summary_memory,
}

self.billing = BillingAgent(llm, **agent_kwargs)
self.product = ProductAgent(llm, **agent_kwargs)
self.orders = OrdersAgent(llm, **agent_kwargs)
self.support = SupportAgent(llm, **agent_kwargs)

for agent in (
    self.billing,
    self.product,
    self.orders,
    self.support,
):
    agent.long_term_memory_manager = self.long_term_memory_manager
```

Essa abordagem evita alterar os construtores de todos os agentes e mantém a funcionalidade encapsulada no framework.

### Configuração do LangGraph

Registre o nó:

```python
builder.add_node(
    "persist_long_term_memory",
    self._node(
        "persist_long_term_memory",
        self.persist_long_term_memory,
    ),
)
```

Altere o fluxo:

```python
builder.add_edge(
    "supervisor_review",
    "persist_long_term_memory",
)
builder.add_edge(
    "persist_long_term_memory",
    "persist",
)
```

Implemente o método:

```python
async def persist_long_term_memory(
    self,
    state: AgentState,
) -> dict[str, object]:
    result = await self.long_term_memory_manager.persist_turn(state)

    return {
        "long_term_memory_write_result": result,
    }
```

Fluxo final:

```text
supervisor_review
        │
        ▼
persist_long_term_memory
        │
        ▼
persist
```

### Variáveis de ambiente

```env
ENABLE_LONG_TERM_MEMORY=true

LONG_TERM_MEMORY_PROVIDER=sqlite
LONG_TERM_MEMORY_SQLITE_PATH=./data/agent_framework.db
LONG_TERM_MEMORY_TABLE=agentfw_long_term_memory

LONG_TERM_MEMORY_MAX_CONTEXT_ITEMS=20
LONG_TERM_MEMORY_MIN_CONFIDENCE=0.70
LONG_TERM_MEMORY_AUTO_EXTRACT=true
LONG_TERM_MEMORY_INJECT_CONTEXT=true
```

### Caminho do banco SQLite

O caminho relativo é resolvido a partir do diretório em que o backend é iniciado.

Para evitar que bancos diferentes sejam criados acidentalmente, prefira um caminho absoluto em ambientes de desenvolvimento:

```env
LONG_TERM_MEMORY_SQLITE_PATH=/mnt/c/Asus_Projects/agent_platform_oci_long_term_memory/data/agent_framework.db
```

Crie a pasta antes de iniciar:

```bash
mkdir -p data
```

### Como testar

### Teste 1 — Gravação

Envie:

```json
{
  "session_id": "default:telecom_contas:memory-session-a",
  "customer_key": "11999999999",
  "message": "Me chame de Cris. Minha linguagem preferida é Python e meu projeto atual se chama Atlas."
}
```

### Teste 2 — Recuperação em outra sessão

Utilize outro `session_id`, mantendo o mesmo `customer_key`:

```json
{
  "session_id": "default:telecom_contas:memory-session-b",
  "customer_key": "11999999999",
  "message": "O que você lembra sobre mim, minhas preferências e meu projeto?"
}
```

Resultado esperado:

```text
Seu nome preferido é Cris.
Sua linguagem preferida é Python.
Seu projeto atual se chama Atlas.
```

### Teste 3 — Isolamento

Utilize outro cliente:

```json
{
  "session_id": "default:telecom_contas:memory-session-c",
  "customer_key": "outro-cliente",
  "message": "Qual é meu nome preferido e qual é meu projeto atual?"
}
```

Os dados de `11999999999` não devem aparecer.

### Teste 4 — Reinicialização do frontend

Reinicie ou resete o frontend e confirme que ele continua enviando o mesmo `customer_key`.

A memória deve sobreviver à troca do `session_id`. O reset do frontend não apaga o SQLite.

### Teste 5 — Reinicialização do backend

Reinicie o Uvicorn e repita a consulta.

Com:

```env
LONG_TERM_MEMORY_PROVIDER=sqlite
```

a memória deve continuar disponível.

Com:

```env
LONG_TERM_MEMORY_PROVIDER=memory
```

a memória será perdida quando o processo for encerrado.

### Verificação direta no SQLite

Localize o banco:

```bash
find . -name "agent_framework.db" -type f
```

Abra:

```bash
sqlite3 ./data/agent_framework.db
```

Consulte:

```sql
SELECT
    tenant_id,
    agent_id,
    customer_key,
    memory_type,
    memory_key,
    memory_value,
    confidence,
    created_at,
    updated_at
FROM agentfw_long_term_memory
ORDER BY updated_at DESC;
```

### Critérios de sucesso

A implementação está funcionando quando:

- a memória é recuperada com outro `session_id`;
- o mesmo `customer_key` recupera os fatos anteriores;
- outro `customer_key` não acessa esses fatos;
- reiniciar o frontend não apaga a memória;
- reiniciar o backend não apaga a memória quando o provider é SQLite;
- o nó `persist_long_term_memory` é executado;
- o prompt recebe `long_term_memory_context`.

### Boas práticas

- Persistir somente fatos duradouros.
- Não armazenar a conversa completa como Long-Term Memory.
- Isolar dados por `tenant_id`, `agent_id` e `customer_key`.
- Não utilizar `session_id` como identidade permanente do usuário.
- Persistir somente depois das validações finais.
- Evitar armazenar resultados temporários de ferramentas.
- Registrar telemetria de leitura, escrita, atualização e falha.
- Definir políticas de retenção e exclusão.
- Usar caminho absoluto para SQLite em ambientes com múltiplos diretórios de execução.
- Migrar para um banco corporativo em ambientes de produção e alta disponibilidade.

### Limitações da implementação de referência

A implementação atual utiliza extração baseada em regras e SQLite como provider de referência.

Evoluções recomendadas:

- extração de fatos com LLM;
- memória semântica com vetores;
- memória episódica;
- expiração e versionamento;
- deduplicação semântica;
- política de consentimento;
- API de consulta e exclusão;
- provider Oracle Autonomous Database;
- criptografia e classificação de dados sensíveis.
