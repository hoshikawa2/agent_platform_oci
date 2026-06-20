# OCI Instance Principal and FastMCP support

This version adds two framework capabilities:

1. OCI SDK authentication with `OCI_AUTH_MODE=instance_principal`.
2. Official MCP/FastMCP client transport in addition to the legacy HTTP mock contract.

## OCI authentication

Supported values:

```env
OCI_AUTH_MODE=config_file          # local ~/.oci/config profile, default
OCI_AUTH_MODE=instance_principal   # OCI Compute / OKE workload identity via instance principal
OCI_AUTH_MODE=resource_principal   # OCI Functions / resource principal contexts
```

For local development, keep:

```env
LLM_PROVIDER=oci_openai
OCI_GENAI_API_KEY=...
```

For OCI runtimes without API keys, use the SDK provider:

```env
LLM_PROVIDER=oci_sdk
OCI_AUTH_MODE=instance_principal
OCI_COMPARTMENT_ID=ocid1.compartment.oc1...
OCI_REGION=sa-saopaulo-1
OCI_GENAI_MODEL=cohere.command-r-plus
```

The same `OCI_AUTH_MODE` is also used by the OCI embedding provider:

```env
EMBEDDING_PROVIDER=oci
OCI_AUTH_MODE=instance_principal
OCI_COMPARTMENT_ID=ocid1.compartment.oc1...
OCI_EMBEDDING_MODEL=cohere.embed-multilingual-v3.0
```

> Note: `oci_openai` continues to use the OpenAI-compatible endpoint and API key. Instance principal is implemented through `oci_sdk` because it needs OCI request signing.

## FastMCP transport

The previous framework MCP client remains available:

```yaml
servers:
  telecom:
    transport: http
    endpoint: http://localhost:8001/mcp
```

For FastMCP / official MCP Streamable HTTP:

```yaml
servers:
  telecom:
    transport: fastmcp
    endpoint: http://localhost:8001/mcp
```

For MCP SSE:

```yaml
servers:
  telecom:
    transport: sse
    endpoint: http://localhost:8001/sse
```

Tools still use `tools.yaml` and `mcp_parameter_mapping.yaml`. Only the server transport changes.
