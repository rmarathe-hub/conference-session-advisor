# Architecture — Two Deliverables

Project: **Conference Session Advisor**

Purpose: *Builds a practical agenda from priorities found in Microsoft 365 context and maps those priorities to grounded Microsoft Build sessions.*

The system has **exactly two** major deliverables. Nothing else is a primary component.

```
Microsoft 365 Copilot (host)
        │
        │  declarative agent (Component A)
        │  Email / TeamsMessages / Meetings /
        │  OneDriveAndSharePoint / People
        │
        ▼
   MCP HTTP (/mcp)
        │
        ▼
Python/FastAPI MCP server (Component B)
        │
        ▼
CatalogService (scoring, normalization, cache)
        │
        ▼
npx @microsoft/events-cli  →  build-2026 catalog
```

---

## Component A — Declarative agent (1.1)

**What it is:** A Microsoft 365 Copilot declarative agent defined entirely through JSON configuration. There is **no server-side bot code**.

**Role:**
1. Read the user’s Microsoft 365 context (Email, TeamsMessages, Meetings, OneDriveAndSharePoint, People).
2. Extract priorities, challenges, initiatives, and pain points into atomic signals.
3. Normalize and rank signals by importance.
4. Call the MCP server’s `match_sessions` (and `get_session_by_code` when needed).
5. Compose an agenda grouped by signal from **tool-returned metadata only**.

**Package files (built later):**
- `manifest.json`
- `declarativeAgent.json`
- `conferenceCatalogPlugin.json`
- `conferenceCatalogTools.json`
- `color.png` (192×192), `outline.png` (32×32)

**Grounding (Layer 1):** Instructions and plugin text must forbid invented sessions. Recommendations come only from MCP tool results. Empty enterprise context → `No enterprise data found.` Empty matches → say there is no grounded match; do not guess.

**Runtime:** Copilot hosts the agent. The plugin uses `RemoteMCPServer` with `spec.url` pointing at the **deployed** MCP endpoint (`https://<appName>.azurewebsites.net/mcp`). PoC auth is `auth.type = None` (document production auth requirement; do not implement custom auth in the base project).

Component A is a **thin configuration layer**. It does not own the catalog.

---

## Component B — MCP server (1.2)

**What it is:** A Python/FastAPI MCP server that returns grounded Microsoft Build session matches.

**Package layout:**
```
conferenceCatalogMCP/
    __init__.py
    service.py      # CatalogService
    server.py       # FastAPI + JSON-RPC MCP + REST helpers
    blob_cache.py   # Azure Blob TTL cache
requirements.txt
Dockerfile
```

**HTTP surface (exactly):**
- `GET /healthz` → `{ "status": "ok" }`
- `POST /mcp` — JSON-RPC 2.0 (`initialize`, `notifications/initialized`, `tools/list`, `tools/call`)
- `POST /tools/list` — REST convenience
- `POST /tools/call` — REST convenience

**MCP tools (exactly two):**
- `match_sessions`
- `get_session_by_code`

**CatalogService responsibilities:**
- Sole CLI access via `_run_events_cli_json(args)` → `npx -y @microsoft/events-cli …` for **build-2026**
- Scoring, normalization, transcript resolution, `whyItMaps`
- Caching (in-process TTL, then Azure Blob) before CLI

**Grounding (Layer 2):** Only sessions produced by `@microsoft/events-cli` for `build-2026` may be returned. No alternate catalog sources; no fabricated sessions.

**Independence:** Component B must be runnable and testable **without** Component A (local uvicorn, container, then Azure).

---

## Build order and dependency rule (1.3)

| Rule | Detail |
|------|--------|
| Build B before A | Implement and verify the MCP server locally, in a container, and in Azure before building the declarative agent. |
| B is independently testable | Smoke JSON-RPC and tools without Copilot or the agent package. |
| A depends on deployed B | Agent `spec.url` points at the live `/mcp` URL after Azure deploy. |
| No extra deliverables | No frontend app, no extra MCP tools/endpoints, no schedule-aware agenda, no custom auth system in the base project. |

### Runtime flow (locked)

1. Agent runs inside Microsoft 365 Copilot.
2. Agent gathers user/customer context with Microsoft 365 capabilities.
3. Agent converts context into normalized signals.
4. Agent calls the MCP server for each signal.
5. MCP server returns grounded Build matches.
6. Agent composes the agenda from returned metadata.

### Next implementation target

**Component B** — scaffold and implement `conferenceCatalogMCP` for local smoke testing (`uvicorn` on port 8010).
