# External Guardrails / Judges

Este cenário de tuning mede extensões de política do agente. Antes de interpretar os resultados, implemente e valide o contrato descrito no [guia completo](../../docs/EXTERNAL_GUARDRAILS_JUDGES.md).

O cenário deve comparar, no mínimo, latência p50/p95/p99, taxa de allow/deny/sanitize, erros e timeouts, custo de judges com LLM e comportamento fail-open/fail-closed. Separe resultados por código/nome e estágio, sem registrar prompts, PII ou payloads financeiros.

Cuidados de leitura:

- `type: external` afeta apenas o componente declarado;
- implementação síncrona usa worker thread e implementação `async` usa o event loop;
- judges executam concorrentemente, então meça contenção do provedor e do pool;
- compare a mesma carga com extensão desligada para obter o overhead incremental;
- execute casos transacionais separadamente, pois `always_run_for_transactional` ignora a amostragem;
- no template corrente os pipelines são globais; caminhos por agente não implicam isolamento automático.

Antes do benchmark, rode `pytest -q tests/test_external_guardrails_judges_documentation.py` para provar que os exemplos do manual ainda carregam e executam.
