# SPEC-015 — Adoption and Eligibility Criteria

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

Critérios de adoção definem quando um projeto deve usar a Agent Platform OCI e quais requisitos mínimos precisa atender para entrar em desenvolvimento, homologação e produção.

# 2. Problema que resolve

Sem critérios claros:

- qualquer caso simples vira agente;
- projetos sem owner entram na plataforma;
- canais entram sem contrato;
- agentes entram sem dataset;
- produção ocorre sem evaluator;
- operação fica sem dashboard/alerta.

# 3. Casos indicados

| Caso | Exemplo |
| --- | --- |
| Agentes conversacionais | Atendimento, suporte, backoffice. |
| Multiagentes | Handoff entre domínios. |
| Agentes com tools | Consulta/ação em sistemas. |
| Agentes com RAG | Uso de documentos e políticas. |
| Ambientes regulados | Necessidade de governança e auditoria. |
| Canais corporativos | Web, WhatsApp, Voice, URA, CRM. |


# 4. Casos não indicados

| Caso | Motivo |
| --- | --- |
| CRUD simples | API REST sem IA. |
| ETL batch | Pipeline de dados. |
| Job agendado simples | Sem interação. |
| Serviço utilitário | Validação/formatação simples. |
| Integração sem decisão | Proxy API sem raciocínio. |


# 5. Critérios de entrada de negócio

Antes de iniciar:

- business owner;
- technical owner;
- objetivo;
- escopo;
- fora de escopo;
- canais;
- sistemas;
- documentos;
- critérios de sucesso;
- riscos.

# 6. Critérios de arquitetura

Obrigatórios:

- GatewayRequest;
- ChannelResponse;
- BusinessContext;
- health/readiness;
- logs;
- traces;
- dataset;
- evaluator;
- certification.

# 7. Critérios de segurança

Obrigatórios:

- autenticação;
- autorização;
- secrets externos;
- máscara de PII;
- auditoria;
- revisão de risco.

# 8. Critérios de qualidade

Obrigatórios:

- testes unitários;
- testes de integração;
- dataset;
- evaluator;
- thresholds;
- certification.

# 9. Critérios de operação

Obrigatórios:

- métricas;
- dashboards;
- alertas;
- runbook;
- rollback;
- SLO.

# 10. Processo de exceção

Exceções permitidas:

- sem RAG;
- sem MCP;
- sem memória;
- sem handoff;
- sem canal externo.

Toda exceção deve registrar:

```yaml
exception:
  reason: "Agente não usa documentos"
  approved_by: architecture
  expires_at: 2026-12-31
```

# 11. Checklist de adoção

- [ ] Business owner definido.
- [ ] Technical owner definido.
- [ ] Escopo definido.
- [ ] Casos fora de escopo definidos.
- [ ] GatewayRequest definido.
- [ ] BusinessContext definido.
- [ ] Segurança definida.
- [ ] Dataset criado.
- [ ] Evaluator configurado.
- [ ] Certification planejada.
- [ ] Observabilidade planejada.

# 12. Critérios de aceite

- [ ] Projeto elegível para plataforma.
- [ ] Requisitos mínimos atendidos.
- [ ] Exceções documentadas.
- [ ] Plano de homologação definido.
- [ ] Critérios de produção definidos.
