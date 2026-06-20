"""Regras canônicas de vocalização TTS para agentes TIM.

Bloco de texto reutilizável que todos os prompts de guardrail/supervisão
que produzem texto para o cliente devem incluir via interpolação.
"""

TTS_RULES = """
REGRAS DE VOCALIZAÇÃO (obrigatórias para texto que será lido em voz alta):
- Números: escreva por extenso. Ex.: "R$ 12,50" → "doze reais e cinquenta centavos".
- Datas: por extenso. Ex.: "05/04/2026" → "cinco de abril de dois mil e vinte e seis".
- Telefones: dígito a dígito. Ex.: "11 9 8765-4321" → "um um, nove, oito sete seis cinco, quatro três dois um".
- Protocolos: dígito a dígito. Ex.: "PRT-4521" → "pê erre tê, quatro cinco dois um".
- Nunca use markdown (*, **, #, listas com traço ou número).
- Nunca inicie frase com "Entendido,", "Claro,", "Certamente," (false-start).
- Máximo 3 frases na resposta; prefira 1-2.
"""

__all__ = ["TTS_RULES"]
