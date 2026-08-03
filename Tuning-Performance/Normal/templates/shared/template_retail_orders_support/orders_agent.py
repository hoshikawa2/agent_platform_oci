class OrdersAgent:
    name = "orders_agent"

    def __init__(self, llm, telemetry=None):
        self.llm = llm
        self.telemetry = telemetry

    async def run(self, state):
        # EXEMPLO DO TEMPLATE 2: agente de pedidos/e-commerce.
        # Substitua por tools reais: consultar_pedido, rastrear_entrega,
        # solicitar_devolucao, consultar_nota_fiscal etc.
        messages = [
            {"role": "system", "content": "Você é especialista em pedidos, entrega e devolução."},
            {"role": "user", "content": state.get("sanitized_input") or state["user_text"]},
        ]
        answer = await self.llm.ainvoke(messages)
        return {"answer": f"[OrdersAgent] {answer}", "next_state": "ORDER_ACTIVE"}
