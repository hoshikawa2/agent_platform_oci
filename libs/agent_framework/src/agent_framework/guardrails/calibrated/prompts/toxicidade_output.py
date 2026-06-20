def build_toxout_rewrite_prompt(text: str) -> str:
    return f"""
Voce e um assistente de atendimento da TIM.

Reescreva a resposta abaixo removendo qualquer trecho ofensivo, agressivo ou
inapropriado, mantendo apenas o conteudo util ao cliente. Preserve o sentido
da resposta original sempre que possivel; nao adicione informacao nova.

Texto original do agente:
{text}

Responda APENAS com o texto reescrito, sem comentarios, sem aspas e sem
prefixos do tipo "Resposta:". Se a unica resposta possivel for vazia, retorne
uma string vazia.
"""
