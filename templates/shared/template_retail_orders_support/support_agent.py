class SupportAgent:
    name = "support_agent"

    def __init__(self, llm, telemetry=None):
        self.llm = llm
        self.telemetry = telemetry

    async def run(self, state):
        # EXEMPLO DO TEMPLATE 2: agente de suporte geral.
        # Substitua por tools reais: reset_senha, validar_pagamento,
        # consultar_cupom, abrir_ticket etc.
        messages = [
            {"role": "system", "content": "Você é especialista em suporte de conta, pagamento e uso do site."},
            {"role": "user", "content": state.get("sanitized_input") or state["user_text"]},
        ]
        answer = await self.llm.ainvoke(messages)
        return {"answer": f"[SupportAgent] {answer}", "next_state": "SUPPORT_ACTIVE"}
