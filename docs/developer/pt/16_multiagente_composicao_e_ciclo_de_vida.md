### Multiagente, composição e ciclo de vida

### O que constitui um agente isolado

Um `agent_id` não é apenas um label. O isolamento real precisa abranger prompt, routing, tools, MCP servers, guardrails, judges, memória, checkpoints, cache, telemetria e identidade. A chave operacional recomendada é `tenant_id:agent_id:session_id`.

```yaml agents-registry-example
default_agent_id: financial
agents:
  - agent_id: financial
    name: Agente Financeiro
    description: Consultas e operações financeiras.
    prompt_policy_path: ./config/agents/financial/prompt_policy.yaml
    routing_config_path: ./config/agents/financial/routing.yaml
    guardrails_config_path: ./config/agents/financial/guardrails.yaml
    judges_config_path: ./config/agents/financial/judges.yaml
    mcp_servers_config_path: ./config/agents/financial/mcp_servers.yaml
    tools_config_path: ./config/agents/financial/tools.yaml
    metadata:
      domain: financial
      system_prefix: |
        Execute somente políticas e recursos do agent_id financial.
```

Todos os caminhos devem existir e ser validados no startup. O prefixo ajuda o LLM, mas não é barreira de segurança. Autorização de tools, namespaces de persistência e seleção de pipelines devem ser impostas pelo código.

### Limitação real do template atual

O registry aceita esses caminhos, mas o `AgentWorkflow` corrente ainda constrói um único router, um único conjunto de tools/RAG e um par global de guardrails/judges. Portanto, copiar o YAML acima não cria isolamento completo por requisição. Até existir uma factory/cache por perfil, use uma configuração global por deployment ou implemente a seleção explícita antes de invocar o grafo.

Uma composição correta mantém, por `agent_id`, os objetos imutáveis/caros em cache e injeta dependências na execução:

```python agent-runtime-bundle-example
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentRuntimeBundle:
    router: Any
    tool_router: Any
    rag_service: Any
    guardrails: Any
    judges: Any


def select_bundle(registry: dict[str, AgentRuntimeBundle], agent_id: str) -> AgentRuntimeBundle:
    if agent_id not in registry:
        raise KeyError(f"agent_id não registrado: {agent_id}")
    return registry[agent_id]
```

Não construa LLM, conexão, router ou pipeline a cada mensagem. Não use fallback silencioso para o bundle de outro agente; falhe de forma explícita ou use somente o `default_agent_id` autorizado na borda.

### Subagentes e supervisor

Subagente é uma capacidade delimitada, não apenas uma função Python. Declare objetivo, entradas, saídas, tools autorizadas, orçamento/timeout e condições de retorno. O supervisor recebe resultados estruturados e consolida; ele não deve compartilhar todo o histórico por padrão. Uma delegação deve carregar correlação e profundidade máxima para evitar ciclos.

Use router quando uma única especialidade resolve o turno. Use supervisor quando a tarefa realmente exigir decomposição ou combinação de duas ou mais capacidades. Para handoff, transfira propriedade da conversa; para subagente, mantenha o supervisor como proprietário da resposta final.

### Composição de LLM por domínio

Use `llm_profiles.yaml` e o cliente criado pelo framework. Componentes recebem `profile_name` ou o LLM compartilhado; não criam SDK/provedor com credenciais próprias. Isso preserva autenticação, rate limits, retries, cache e telemetria. Fallback entre profiles precisa ser explícito e observável; nunca converta falha de configuração em resposta aparentemente válida.

### RAG e memória por agente

`RAG_PROVIDER=kbdb` seleciona KBDB apenas quando o `RagService` daquela execução usa as settings corretas. A intenção simples também deve acionar RAG quando a política do agente exigir conhecimento. Separe coleção/namespace por tenant e agente. Memória de longo prazo guarda fatos permitidos e resumidos; checkpoint guarda execução. Nenhum dos dois deve misturar identidade de outro agente.

### Autenticação e autorização

Autenticação prova o principal; autorização decide agente, tenant, rota e tool. Basic, API key, bearer, JWT, introspection e trusted proxy são providers possíveis, mas produção deve usar segredo com hash/rotação e TLS. Headers de trusted proxy só são confiáveis quando a borda autenticada remove valores enviados pelo cliente.

### Inicialização e readiness

No startup: validar registry e caminhos; criar providers; registrar actions/renderers; carregar workflows; construir bundles; verificar conexões essenciais. `/ready` deve falhar quando uma dependência obrigatória não estiver utilizável; `/health` indica processo vivo. Configuração inválida deve falhar cedo, antes da primeira conversa.

### Ciclo de desenvolvimento e certificação

1. Copiar o template canônico sem copiar `.venv` ou caches.
2. Criar agente, estado somente se necessário, configurações e recursos de domínio.
3. Registrar nó/rota e decidir router ou supervisor.
4. Implementar tools, mappings, políticas, actions e renderers.
5. Configurar guardrails, judges, RAG, memória e observabilidade.
6. Testar unidade, loader/config, grafo, regressão conversacional e falhas.
7. Executar avaliação offline, carga e readiness.
8. Publicar com versão, compatibilidade e rollback documentados.

### Definition of done

Um agente não está pronto apenas porque responde ao happy path. Ele precisa provar isolamento, confirmação antes de efeito, idempotência, recuperação, grounding, bloqueio/sanitização, telemetria correlacionada, ausência de vazamento, comportamento sob dependência indisponível e compatibilidade PT/EN dos manuais.

Os contratos deste capítulo são validados por `tests/test_advanced_developer_documentation.py`.

