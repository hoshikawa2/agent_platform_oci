# FastMCP mode

This folder keeps the original FastAPI mock server in `main.py` and adds an official FastMCP server in `main_fastmcp.py`.

Run legacy mock HTTP contract:

```bash
uvicorn main:app --host 0.0.0.0 --port 8001
```

Run FastMCP Streamable HTTP:

```bash
python main_fastmcp.py
```

In the framework, point `config/mcp_servers.yaml` to the FastMCP endpoint and set:

```yaml
transport: fastmcp
endpoint: http://localhost:8001/mcp
```
