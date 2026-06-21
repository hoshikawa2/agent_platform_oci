FROM python:3.12-slim

WORKDIR /app

COPY apps/mcp_gateway/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY apps/mcp_gateway/app /app/app
COPY apps/mcp_gateway/config /app/config

ENV MCP_GATEWAY_CONFIG_PATH=/app/config/mcp_gateway.yaml

EXPOSE 8300

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8300"]
