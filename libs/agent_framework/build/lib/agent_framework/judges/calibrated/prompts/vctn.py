def build_vctn_prompt(text):
    return f"""
Avalie o tom de voz do agente.

Regra:
- Deve ser educado
- Não pode ser rude ou agressivo

Texto:
{text}

Classifique:
- Adequado
- Inadequado

Responda JSON:
{{
  "allowed": true,
  "label": "Adequado/Inadequado",
  "reason": "explicação"
}}
"""