# Azure Deployment

Completed deployment of the Conference Catalog MCP server to Azure App Service as a custom Linux container. The image is built with ACR Tasks and stored in Azure Container Registry. CatalogService uses a two-tier cache: in-process TTL plus Azure Blob Storage.

## Architecture Summary

```
Client / Copilot plugin
        │
        ▼
Azure App Service (Linux custom container)
  rmarathe-conf-advisor-7672
  WEBSITES_PORT=8010
        │
        ├── pulls image from ACR (managed identity + AcrPull)
        │
        └── CatalogService
              ├── in-process TTL cache
              ├── Azure Blob cache (mcp-cache) via managed identity
              └── npx @microsoft/events-cli → build-2026
```

Public endpoints:

- Health: https://rmarathe-conf-advisor-7672.azurewebsites.net/healthz
- MCP JSON-RPC: https://rmarathe-conf-advisor-7672.azurewebsites.net/mcp

## Azure Resources

| Item | Value |
|------|-------|
| Resource group | `rg-conference-session-advisor` |
| Region | `westus2` |
| Azure Container Registry | `rmaratheconfacr7672` (Basic; admin disabled) |
| App Service plan | `asp-conference-session-advisor` (Linux, B1) |
| Web App | `rmarathe-conf-advisor-7672` |
| Storage account | `rmarathecache7672` (Standard_LRS, StorageV2) |
| Blob container | `mcp-cache` (private; public access disabled) |

## Container Image

| Item | Value |
|------|-------|
| Image | `rmaratheconfacr7672.azurecr.io/conferencecatalog-mcp:latest` |
| Build method | Azure Container Registry Tasks (`az acr build`) |
| Runtime | Multi-stage `python:3.12-slim` with Node.js 22 / npm / `npx` in the **final** stage |
| Process | `uvicorn conferenceCatalogMCP.server:app --host 0.0.0.0 --port 8010` |
| Healthcheck target | `/healthz` |

The App Service listens on port **8010** (`WEBSITES_PORT=8010`) and pulls the image using managed identity (not ACR admin credentials).

## Managed Identity and RBAC

The Web App uses:

- **System-assigned managed identity**
- **AcrPull** on the Azure Container Registry (`rmaratheconfacr7672`)
- **Storage Blob Data Contributor** on the Storage account (`rmarathecache7672`)
- **No ACR admin credentials**
- **No Storage connection string**

`acrUseManagedIdentityCreds=true`. Image pull and Blob cache access use managed identity / `DefaultAzureCredential` and Azure RBAC only.

## App Settings

| Setting | Value |
|---------|-------|
| `WEBSITES_PORT` | `8010` |
| `AZURE_STORAGE_ACCOUNT_NAME` | `rmarathecache7672` |
| `MCP_CACHE_CONTAINER` | `mcp-cache` |
| `MCP_MATCH_CACHE_TTL_SECONDS` | `300` |
| `MCP_DETAIL_CACHE_TTL_SECONDS` | `900` |
| `EVENTS_CLI_TIMEOUT_SECONDS` | `90` |

## Deployment Procedure

High-level procedure used for this environment (non-secret names only):

1. Create resource group `rg-conference-session-advisor` in `westus2`.
2. Create ACR `rmaratheconfacr7672` (Basic, admin disabled).
3. Build and push the image with ACR Tasks to `conferencecatalog-mcp:latest`.
4. Create storage account `rmarathecache7672` and private blob container `mcp-cache`.
5. Create Linux App Service plan `asp-conference-session-advisor` (B1) and Web App `rmarathe-conf-advisor-7672` pointing at the ACR image.
6. Enable system-assigned managed identity on the Web App.
7. Grant **AcrPull** on the registry; enable managed-identity ACR pull (`acrUseManagedIdentityCreds=true`).
8. Grant **Storage Blob Data Contributor** on the storage account.
9. Set the App Settings listed above (including `WEBSITES_PORT=8010`).
10. Enable container logging, restart the Web App, and verify `GET /healthz`.

## Verification Results

Verified against the deployed Web App (live re-check 2026-07-13, Phase 5E):

- `GET /healthz` returned HTTP 200 with `{"status":"ok"}`
- MCP `initialize` returned `protocolVersion` `2024-11-05` and `serverInfo.name` `conference-catalog-mcp`
- `tools/list` returned exactly `match_sessions` and `get_session_by_code`
- `match_sessions` for signal  
  `Natural language interface to enterprise data using Power BI semantic models and Fabric Data Agents.`  
  returned sessionCode `OD812` (asset: Fabric IQ: Bringing enterprise intelligence into the developer workflow), with recording, transcript, `matchScore`, `catalogVersion`, and both `content` and `structuredContent`
- `get_session_by_code` returned full normalized metadata for `OD812`
- Empty signal returned JSON-RPC error `-32602`
- Unknown session code returned JSON-RPC error `-32001`
- Blob list on `mcp-cache` returned ≥1 blob names (auth-mode login; no keys)
- App settings present by **name**: `WEBSITES_PORT`, `AZURE_STORAGE_ACCOUNT_NAME`, `MCP_CACHE_CONTAINER`, `MCP_MATCH_CACHE_TTL_SECONDS`, `MCP_DETAIL_CACHE_TTL_SECONDS`, `EVENTS_CLI_TIMEOUT_SECONDS`; `linuxFxVersion` = `DOCKER|rmaratheconfacr7672.azurecr.io/conferencecatalog-mcp:latest`; `acrUseManagedIdentityCreds` enabled
- RBAC role **names** on scoped resources: **AcrPull** (ACR), **Storage Blob Data Contributor** (storage); Web App identity type **SystemAssigned**
- After a Web App restart (earlier verify): `GET /healthz` still returned `{"status":"ok"}`; `get_session_by_code` and error handling still worked

## Persistent Cache Verification

- Cache tiers: **in-process TTL** and **Azure Blob** (`mcp-cache` on `rmarathecache7672`).
- Blob access uses managed identity / `DefaultAzureCredential` with `AZURE_STORAGE_ACCOUNT_NAME` (no connection string).
- Container `mcp-cache` exists and contained Blobs for live `match_sessions` / detail keys after use (names only; no payload dumps).
- Health and MCP tool/error behavior survived a Web App restart (see Verification Results).
- **5E+ live cache evidence (2026-07-13):** two identical `match_sessions` calls with a fresh Fabric signal suffix → first call ~9.8s (CLI path), second call ~0.11s same `OD812` envelope. That cold→warm timing plus Blob entries is treated as Cache HIT evidence. App Service log stream showed uvicorn access lines only; the literal application log string `Cache HIT` was not captured in container log tail (Python app logger is not wired to stdout in the image). Do not invent a log-line claim beyond what was observed.

## Operational Commands

Safe, non-secret operations:

```bash
RG="rg-conference-session-advisor"
ACR="rmaratheconfacr7672"
APP="rmarathe-conf-advisor-7672"
STORAGE="rmarathecache7672"
HEALTH_URL="https://rmarathe-conf-advisor-7672.azurewebsites.net/healthz"
MCP_URL="https://rmarathe-conf-advisor-7672.azurewebsites.net/mcp"

# Web App status
az webapp show --resource-group "$RG" --name "$APP" --query "{state:state,defaultHostName:defaultHostName}" -o json

# Restart
az webapp restart --resource-group "$RG" --name "$APP"

# Health
curl -sS "$HEALTH_URL"

# MCP initialize
curl -sS -X POST "$MCP_URL" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'

# MCP tools/list
curl -sS -X POST "$MCP_URL" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'

# List cache blobs (auth-mode login; no keys)
az storage blob list \
  --account-name "$STORAGE" \
  --container-name mcp-cache \
  --auth-mode login \
  -o table

# Logs
az webapp log tail --resource-group "$RG" --name "$APP"

# Rebuild image in ACR (from repo root with Dockerfile)
az acr build \
  --registry "$ACR" \
  --image conferencecatalog-mcp:latest \
  --file Dockerfile \
  .

# After a new image: restart the Web App so it pulls latest
az webapp restart --resource-group "$RG" --name "$APP"
```

Kudu / SCM: https://rmarathe-conf-advisor-7672.scm.azurewebsites.net

ACR tags:

```bash
az acr repository show-tags \
  --name rmaratheconfacr7672 \
  --repository conferencecatalog-mcp
```

## Security Notes

- `/mcp` currently has **no application-level authentication**. Callers who know the public URL can invoke the MCP endpoint.
- Authentication implementation is **intentionally outside the scope of this project**.
- Managed identity and Azure RBAC secure App Service access to ACR and Blob Storage, but **do not authenticate public MCP callers**.
- Do **not** implement authentication inside this project as part of the base Conference Session Advisor work.
- This document intentionally excludes secrets and private Azure identifiers (subscription IDs, tenant IDs, principal IDs, tokens, storage keys, connection strings, and registry passwords).

## Cleanup Instructions

To remove the deployed environment when it is no longer needed:

```bash
az group delete \
  --name rg-conference-session-advisor \
  --yes \
  --no-wait
```

Deleting the resource group removes the App Service plan, Web App, ACR, storage account, and related role assignments scoped to those resources. Confirm the resource group name before running delete.
