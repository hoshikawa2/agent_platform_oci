from fastapi import FastAPI

app = FastAPI(title="Mock Telecom MCP Server")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "mock_telecom_mcp"}


@app.post("/tools/consultar_fatura")
async def consultar_fatura(payload: dict):
    return {
        "invoice_id": payload.get("invoice_id") or "INV-001",
        "msisdn": payload.get("msisdn"),
        "valor_total": 249.90,
        "vencimento": "2026-06-10",
        "status": "ABERTA",
    }


@app.post("/tools/consultar_pagamentos")
async def consultar_pagamentos(payload: dict):
    return {
        "msisdn": payload.get("msisdn"),
        "pagamentos": [
            {"data": "2026-06-05", "valor": 249.90, "status": "CONFIRMADO"}
        ],
    }
