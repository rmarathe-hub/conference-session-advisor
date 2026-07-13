# Conference Session Advisor

Builds a practical agenda from priorities found in Microsoft 365 context and maps those priorities to grounded Microsoft Build sessions.

## Deliverables

1. **Component A** — Microsoft 365 Copilot declarative agent (JSON configuration; later phases).
2. **Component B** — Python/FastAPI MCP server that returns grounded Build 2026 sessions via `@microsoft/events-cli`.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Local MCP server

```bash
python3.12 -m pip install -r requirements.txt
python3.12 -m uvicorn conferenceCatalogMCP.server:app --host 127.0.0.1 --port 8010
```

- Health: `GET http://127.0.0.1:8010/healthz`
- MCP: `POST http://127.0.0.1:8010/mcp`

Testing: [docs/TESTING.md](docs/TESTING.md). Prerequisites: [docs/PHASE_0_PREREQUISITES.md](docs/PHASE_0_PREREQUISITES.md).

## Azure Deployment

Live endpoints:

- Health: https://rmarathe-conf-advisor-7672.azurewebsites.net/healthz
- MCP: https://rmarathe-conf-advisor-7672.azurewebsites.net/mcp

Deployed stack: Azure App Service (Linux container) + ACR image `conferencecatalog-mcp:latest` + Blob container `mcp-cache` in `westus2`.

Identity: system-assigned managed identity with **AcrPull** on ACR and **Storage Blob Data Contributor** on Storage (no ACR admin credentials; no storage connection string).

Verified: `/healthz` OK, MCP initialize / tools / `match_sessions` (OD812) / `get_session_by_code`, validation errors, Blob cache entry observed, health and MCP behavior after restart.

Full guide: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).
