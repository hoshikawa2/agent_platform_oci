def build_rqlt_prompt(pergunta, resposta):
    return f"""
Você é um avaliador de qualidade de respostas de atendimento.

Pergunta:
{pergunta}

Resposta:
{resposta}

Critérios:

1. Clareza (0-3)
2. Completude (0-3)
3. Utilidade (0-4)

Regras IMPORTANTES:

- Se a resposta explica corretamente o motivo → score mínimo 6
- Se a resposta é clara e útil → score entre 7 e 9
- Se a resposta é vaga ("não sei", "verifique") → score < 5
- NÃO penalizar respostas curtas se estiverem corretas

Agora avalie.
- BAIXA_QUALIDADE: média de scores abaixo de 4
- BOA_QUALIDADE: média de scores entre 5 e 7
- OTIMA_QUALIDADE: média de scores acima de 8

Responda APENAS JSON:
{{
  "allowed": true,
  "label": "BAIXA_QUALIDADE/BOA_QUALIDADE/OTIMA_QUALIDADE",
  "score": 0-10,
  "reason": "explicação curta"
}}
"""