FROM python:3.11-slim
WORKDIR /app
COPY apps/mcp_gateway/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY apps/mcp_gateway /app
EXPOSE 9200
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9200"]
