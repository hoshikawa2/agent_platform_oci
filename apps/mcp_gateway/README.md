# MCP Gateway

Camada desacoplada para descoberta, roteamento, controle e observabilidade de MCP Servers.

## Rotas

- `GET /health`
- `GET /tools`
- `POST /tools/{tool_name}/invoke`

## Configuração

O arquivo `config/mcp_servers.yaml` define os servidores e ferramentas expostas.
