"""Exemplo de payload para testar o template Telecom."""

payload_fatura = {
    "channel": "web",
    "payload": {
        "text": "Minha fatura veio muito alta este mês, pode explicar?",
        "user_id": "user-001",
        "channel_id": "browser-001",
        "context": {"msisdn": "5511999999999", "invoice_id": "INV-123"},
    },
}

payload_produto = {
    "channel": "web",
    "payload": {
        "text": "Quais serviços VAS estão ativos no meu plano?",
        "user_id": "user-001",
        "channel_id": "browser-001",
        "context": {"msisdn": "5511999999999", "asset_id": "ASSET-123"},
    },
}
