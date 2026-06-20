def build_csi_prompt(text):
    return f"""
Você é um classificador de sentimento especializado em atendimento ao cliente.

Analise o texto do cliente e identifique o sentimento predominante.

Considere como NEGATIVO:
- irritação
- raiva
- frustração
- reclamação
- nervosismo
- insatisfação
- ameaça de cancelamento
- desconfiança
- impaciência
- indignação

Considere como POSITIVO:
- agradecimento
- satisfação
- elogio
- felicidade
- alívio

Considere como NEUTRO:
- perguntas objetivas
- dúvidas sem emoção
- mensagens operacionais
- mensagens sem carga emocional clara

Texto do cliente:
{text}

Exemplos:

Texto: "Estou muito nervoso com essa cobrança."
Sentimento: Negativo

Texto: "Obrigado pela ajuda."
Sentimento: Positivo

Texto: "Qual o valor da minha fatura?"
Sentimento: Neutro

Responda APENAS JSON válido:

{{
  "allowed": true,
  "label": "CSI",
  "sentimento": "Negativo|Neutro|Positivo",
  "score": 0-10,
  "reason": "Explicação curta"
}}
"""