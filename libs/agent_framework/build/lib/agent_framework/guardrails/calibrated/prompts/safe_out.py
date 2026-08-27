def build_safe_out_prompt(response):
    return f"""
Você é um classificador de segurança com objetivo de detectar linguagem ou orientação imprópria na resposta de um agente. 

Resposta:
{response}

Marque UNSAFE_OUT somente se a resposta contiver:
- ofensa, humilhação, discriminação, sarcasmo agressivo ou ameaça ao cliente
- intimidação, pressão indevida ou acusação sem base
- orientação perigosa, ilícita ou para fraudar/burlar sistemas

Marque OK para negativa educada, orientação neutra, cobrança, plano, fatura, oferta, cancelamento ou protocolo dentro do escopo.

Responda JSON:
{{"allowed": true/false, "label": "UNSAFE_OUT/OK", "reason": "Explicação curta da razão"}}
"""

