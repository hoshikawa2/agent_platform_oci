# SPEC-016 — Agent Development Lifecycle

## Agent Platform OCI

Version: 1.0.0


---

## Padrão de leitura

Cada SPEC está organizada para servir tanto como contrato arquitetural quanto como guia prático de adoção.

A estrutura usada é:

1. Conceito.
2. Problema que resolve.
3. Quando usar.
4. Quando não usar.
5. Arquitetura.
6. Implementação.
7. Exemplos.
8. Erros comuns.
9. Critérios de aceite.

---


# 1. Conceito

O ciclo de vida de desenvolvimento de agentes define as etapas desde a descoberta do caso de uso até a operação em produção.

Ele organiza trabalho de produto, arquitetura, engenharia, segurança, avaliação e operação.

# 2. Fluxo do ciclo de vida

```mermaid
flowchart LR
    D[Discovery] --> S[Scope]
    S --> AD[Agent Design]
    AD --> PD[Prompt Design]
    PD --> MD[MCP Design]
    MD --> RD[RAG Design]
    RD --> I[Implementation]
    I --> T[Testing]
    T --> E[Evaluation]
    E --> C[Certification]
    C --> H[Homologation]
    H --> P[Production]
```

# 3. Etapa 1 — Discovery

Objetivo:

- entender problema;
- identificar usuários;
- mapear canais;
- mapear sistemas;
- mapear documentos;
- mapear riscos.

Saída:

```yaml
discovery:
  business_problem: ""
  users: []
  channels: []
  systems: []
  documents: []
  risks: []
```

# 4. Etapa 2 — Scope Definition

Definir:

- o que o agente faz;
- o que não faz;
- intenções;
- ações permitidas;
- limites;
- critérios de sucesso.

# 5. Etapa 3 — Agent Design

Desenhar:

- agent_id;
- rotas;
- intents;
- BusinessContext;
- tools;
- RAG namespaces;
- memória;
- handoff.

# 6. Etapa 4 — Prompt Design

Criar:

- system prompt;
- prompt policy;
- instruções de domínio;
- exemplos;
- restrições;
- formato de resposta.

# 7. Etapa 5 — MCP Design

Definir:

- tools;
- parâmetros;
- owner;
- SLA;
- timeout;
- retry;
- cache;
- operação mutável ou idempotente.

# 8. Etapa 6 — RAG Design

Definir:

- documentos;
- namespace;
- ingestão;
- chunking;
- embeddings;
- atualização;
- critérios de relevância.

# 9. Etapa 7 — Implementation

Implementar:

- classe do agente;
- configs;
- prompts;
- datasets;
- tests;
- observabilidade específica.

# 10. Etapa 8 — Testing

Testes mínimos:

- unit;
- integration;
- contract;
- MCP;
- RAG;
- guardrails;
- judges;
- runtime;
- channel.

# 11. Etapa 9 — Evaluation

Executar:

```bash
af-evaluator run --agent-id <agent_id> --dataset <dataset>
```

Avaliar:

- quality;
- groundedness;
- safety;
- tool correctness;
- route accuracy.

# 12. Etapa 10 — Certification

Executar:

```bash
af-certification run --agent-id <agent_id>
```

# 13. Etapa 11 — Homologation

Validar com:

- negócio;
- arquitetura;
- segurança;
- operação;
- integração.

# 14. Etapa 12 — Production

Requisitos:

- deploy aprovado;
- alertas ativos;
- dashboards ativos;
- rollback validado;
- runbook disponível.

# 15. Erros comuns

| Erro | Impacto | Correção |
| --- | --- | --- |
| Começar pelo código | Escopo mal definido. | Iniciar por discovery/scope. |
| Criar tool antes da intent | Tool sem contexto. | Definir fluxo primeiro. |
| Dataset depois da produção | Sem regressão. | Criar dataset antes da homologação. |
| Prompt sem critérios | Resposta inconsistente. | Definir prompt policy. |


# 16. Critérios de aceite

- [ ] Discovery concluído.
- [ ] Escopo aprovado.
- [ ] Agent design documentado.
- [ ] Prompts criados.
- [ ] MCP design aprovado.
- [ ] RAG design aprovado quando aplicável.
- [ ] Implementação concluída.
- [ ] Testes executados.
- [ ] Evaluator aprovado.
- [ ] Certification aprovada.
- [ ] Homologação concluída.
- [ ] Produção monitorada.
