# IC/NOC/GRL nativo no Langfuse

Esta versão do framework remove a necessidade de um `ics_collector.py` dentro de cada agente.

Agora o próprio framework publica eventos `IC.*`, `AGA.*`, `NOC.*` e `GRL.*` no Langfuse por meio do `AgentObserver` e do `LangfuseAnalyticsPublisher`.

## Configuração

Para publicar IC/NOC/GRL no Langfuse:

```env
ENABLE_LANGFUSE=true
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=http://localhost:3005

# Opcional. Se não informar, ENABLE_LANGFUSE=true já inclui langfuse no observer.
ENABLE_ANALYTICS=true
ANALYTICS_PROVIDERS=langfuse,oci_streaming
```

Para manter compatibilidade com projetos antigos:

```python
from agent_framework.observer import configure

configure({"publisher": {"type": "langfuse"}})
```

## Emissão em agentes nativos

```python
from agent_framework.observer import event, ic, noc, grl

# Mantém o código exatamente como o backoffice original mostrava no Langfuse.
event("AGA.001", data={"sessionId": session_id, "agentId": "backoffice"})

# Também pode usar os atalhos.
ic("AGA.018", data={"missingFields": ["gsm"]})
noc("NOC.001", data={"sessionId": session_id})
grl("GRL.004", data={"rail": "PINJ", "blocked": True})
```

## Comportamento esperado no Langfuse

Cada evento vira uma observation/span com `name` igual ao código:

- `AGA.001`
- `AGA.018`
- `NOC.001`
- `GRL.004`

A metadata recebe automaticamente:

- `tag`
- `ic=true` para `IC.*` e `AGA.*`
- `noc=true` para `NOC.*`
- `grl=true` para `GRL.*`
- `sessionId`, `messageId`, `agentId`, `channelId` quando existirem no payload

## Compatibilidade TIM/FIRST

`ic("AGA.001")` não vira `IC.AGA.001`. O framework preserva `AGA.001`, porque no backoffice original esse era o contrato exibido no Langfuse.

`noc("001")` vira `NOC.001`.

`grl("004")` vira `GRL.004`.
