# Desenvolvimento de agentes

Os arquivos `billing_agent.py`, `product_agent.py`, `orders_agent.py` e `support_agent.py` foram mantidos com os mesmos nomes do template completo para o workflow continuar compatível.

A implementação de negócio original está comentada no final de cada arquivo.

Para criar seu agente:

1. Edite o método `run()` da classe desejada.
2. Use o bloco comentado como referência.
3. Depois, ajuste o roteamento em `config/routing.yaml`.
4. Se quiser renomear classes/arquivos, atualize também os imports em `app/workflows/agent_graph.py`.
