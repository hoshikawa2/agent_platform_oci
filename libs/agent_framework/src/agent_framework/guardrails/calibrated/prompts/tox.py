def build_tox_prompt(text):
    return f"""
Classifique o texto abaixo:

Texto:
{text}

Classifique como:
- TOXICO: Apenas se encontrar palavras ofensivas ou condenatórias
- NORMAL

Responda JSON:
{{
  "allowed": true/false,
  "label": "TOXICO/NORMAL",
  "reason": "razao para a toxicidade"
}}
"""