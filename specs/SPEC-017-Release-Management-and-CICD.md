# SPEC-017 — Release Management and CI/CD

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

Release management define como mudanças entram na plataforma, são testadas, empacotadas, publicadas, promovidas e auditadas.

CI/CD automatiza validações e reduz risco operacional.

# 2. Pipeline padrão

```mermaid
flowchart LR
    C[Commit] --> L[Lint]
    L --> TC[Type Check]
    TC --> UT[Unit Tests]
    UT --> IT[Integration Tests]
    IT --> CT[Contract Tests]
    CT --> SS[Security Scan]
    SS --> B[Build]
    B --> P[Publish]
    P --> DD[Deploy Dev]
    DD --> ST[Smoke Tests]
    ST --> CERT[Certification]
    CERT --> HML[Deploy HML]
    HML --> PROD[Deploy Prod]
```

# 3. Stages

| Stage | Função |
| --- | --- |
| validate | Validação inicial de estrutura. |
| lint | Estilo e erros simples. |
| type_check | Tipos e contratos Python. |
| unit_test | Testes unitários. |
| integration_test | Integrações locais. |
| contract_test | Contratos JSON/YAML/API. |
| security_scan | Dependências, secrets e imagens. |
| build_package | Wheel/package. |
| build_image | Imagem Docker. |
| publish | Registry/artifacts. |
| deploy_dev | Ambiente dev. |
| smoke_test | Health e chamadas básicas. |
| certification | Certification Suite. |
| deploy_hml | Homologação. |
| deploy_prod | Produção. |


# 4. Artefatos de release

- imagem Docker;
- pacote Python;
- release notes;
- matriz de compatibilidade;
- migration guide quando necessário;
- evaluator report;
- certification report;
- SBOM quando aplicável;
- evidência de scan;
- changelog.

# 5. Exemplo de pipeline

```yaml
stages:
  - lint
  - test
  - contract
  - security
  - build
  - publish
  - deploy
  - certification
```

# 6. Gates

| Gate | Quando aplica |
| --- | --- |
| Architecture Gate | Mudanças estruturais, contratos, runtime, gateways. |
| Security Gate | Segredos, identidade, dados sensíveis, MCP externo. |
| Quality Gate | Testes, evaluator, certification. |
| Operations Gate | Dashboards, alertas, runbook, rollback. |


# 7. Estratégia de rollback

Rollback deve restaurar:

- imagem anterior;
- configuração anterior;
- contrato anterior;
- prompt anterior;
- dataset anterior quando necessário;
- migration de banco quando aplicável.

# 8. Erros comuns

| Erro | Impacto | Correção |
| --- | --- | --- |
| Deploy sem certification | Risco funcional. | Rodar certification no pipeline. |
| Sem release notes | Sem rastreabilidade. | Publicar release notes. |
| Sem contract tests | Quebra integração. | Adicionar testes de contrato. |
| Sem rollback | Risco operacional. | Definir estratégia de rollback. |


# 9. Critérios de aceite

- [ ] Pipeline executa lint, type check e testes.
- [ ] Contract tests executam.
- [ ] Security scan executa.
- [ ] Imagem Docker gerada.
- [ ] Artifacts publicados.
- [ ] Smoke tests executados.
- [ ] Certification executada.
- [ ] Release notes publicadas.
- [ ] Rollback definido.
- [ ] Evidências arquivadas.
