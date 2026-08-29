# Agent Template Backend — Pause/Resume Workflow

Exemplo autocontido de um agente que usa o motor genérico de workflows do
`agent_framework_oci`.

O arquivo `workflows/confirmacao.v1.yaml` demonstra:

- `pause`;
- `expected_input`;
- `allowed_values`;
- `normalize`;
- `reprompt`;
- `semantic_classifier`;
- `resume_from`.

O framework não conhece `SIM`, `NAO` nem a regra de negócio. O agente declara
os valores e o prompt no YAML. Quando a fala não corresponde literalmente a uma
opção, `semantic_classifier` classifica usando o prompt do agente e o framework
aceita somente uma saída presente em `allowed_values`; qualquer outra saída usa
o `reprompt`. O mesmo mecanismo funciona com qualquer quantidade de opções.

Execute os testes a partir desta pasta:

```bash
pytest -q
```
