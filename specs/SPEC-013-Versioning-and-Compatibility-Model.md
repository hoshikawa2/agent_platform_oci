# SPEC-013 — Versioning and Compatibility Model

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

Versionamento define como a plataforma evolui sem quebrar projetos existentes. Compatibilidade define quais versões de framework, runtime, gateways, contracts, templates, prompts, tools e evaluator podem operar juntas.

# 2. Problema que resolve

Sem modelo de versionamento:

- uma mudança em GatewayRequest quebra canais;
- uma mudança em MCP tool quebra agentes;
- um prompt alterado muda comportamento sem rastreabilidade;
- evaluator muda score sem histórico;
- templates ficam incompatíveis com runtime;
- produção usa imagem `latest` sem controle.

# 3. Semantic Versioning

Formato:

```text
MAJOR.MINOR.PATCH
```

Regras:

| Parte | Significado |
| --- | --- |
| MAJOR | Mudança incompatível. |
| MINOR | Nova capacidade compatível. |
| PATCH | Correção sem mudança de contrato. |


# 4. Artefatos versionados

| Artefato | Modelo |
| --- | --- |
| agent_framework | SemVer |
| agent_runtime | SemVer alinhado ao framework |
| agent_gateway | SemVer + Docker tag |
| channel_gateway | SemVer + Docker tag |
| ai_gateway | SemVer + Docker tag |
| mcp_gateway | SemVer + Docker tag |
| templates | versão da plataforma |
| contracts | contract-name-vN |
| prompts | SemVer |
| datasets | SemVer |
| guardrails | SemVer por código |
| judges | SemVer por judge |
| mcp_tools | SemVer por tool |
| evaluator | SemVer |
| certification_suite | SemVer + ruleset version |


# 5. Contract versioning

Exemplos:

```text
gateway-request-v1
business-context-v1
tool-invocation-v1
llm-request-v1
```

Permitido na mesma versão major:

- adicionar campos opcionais;
- adicionar metadata;
- adicionar enum documentado.

Não permitido:

- remover campo obrigatório;
- mudar tipo;
- mudar significado;
- alterar regra obrigatória.

# 6. Compatibility Matrix

```yaml
compatibility:
  - framework: "1.4.x"
    runtime: "1.4.x"
    agent_gateway: "1.4.x"
    supported: true
  - framework: "1.4.x"
    runtime: "2.0.x"
    supported: false
```

# 7. Política de depreciação

Ciclo:

```text
Active → Deprecated → Retired
```

Período recomendado:

```text
12 meses
```

# 8. Política de migração

Mudanças major exigem:

- migration guide;
- compatibility matrix;
- rollback strategy;
- certification;
- evaluator;
- release notes.

# 9. Estratégia de rollback

Rollback deve considerar:

- imagem Docker;
- versão do pacote;
- versão dos YAMLs;
- versão do contrato;
- migration de banco;
- dataset;
- prompts.

# 10. Erros comuns

| Erro | Impacto | Correção |
| --- | --- | --- |
| Usar latest em produção | Deploy não reprodutível. | Usar tag explícita. |
| Mudar prompt sem versão | Sem rastreabilidade. | Versionar prompt. |
| Adicionar campo obrigatório em contrato v1 | Quebra clientes. | Criar v2. |
| Atualizar evaluator sem baseline | Scores não comparáveis. | Registrar versão e metodologia. |


# 11. Critérios de aceite

- [ ] Todos os componentes têm versão.
- [ ] Contratos têm versão independente.
- [ ] Matriz de compatibilidade publicada.
- [ ] Release notes publicadas.
- [ ] Migrações major possuem guide.
- [ ] Rollback definido.
- [ ] Prompts e datasets versionados.
- [ ] Evaluator e certification registram versão.
