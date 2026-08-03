payload_pedido = {
    "channel": "web",
    "payload": {
        "text": "Meu pedido atrasou e quero rastrear a entrega.",
        "user_id": "user-002",
        "channel_id": "browser-002",
        "context": {"order_id": "ORDER-123"},
    },
}

payload_suporte = {
    "channel": "web",
    "payload": {
        "text": "Não consigo fazer login e meu cupom não aplica.",
        "user_id": "user-002",
        "channel_id": "browser-002",
        "context": {"customer_id": "CUST-123"},
    },
}
