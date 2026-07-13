# Conference Session Advisor — Phase Checklist

This checklist matches the design contract exactly. Implement required items only; do not add features outside the contract.

**Repository inspected:** 2026-07-12  
**Current state:** Phases 0–6 **COMPLETE** (MCP + Azure + full `app-package` JSON + icons). Agents Toolkit validate/sideload still manual (Phase 7).  
**Active scope now:** Phase 7 (validate, zip, sideload, conversation starters).

**Out of scope for the base project (do not implement):**
- Extra product features, embedding search, vector databases
- Schedule-aware / time-ordered agenda generation
- Conflict detection, analytics dashboards, metrics endpoints
- CI/CD, GitHub Actions, Docker Compose
- API-key middleware, OAuth, custom authentication systems
- Additional cloud services, MCP tools, REST endpoints, ranking algorithms, databases, frontends
- Explicit numeric SLOs (nice-to-have only)

---

## Phase 0 — Prerequisites

| ID | Requirement | Status |
|----|-------------|--------|
| 0.1 | Inspect repository; create this phase-by-phase checklist | **Done** |
| 0.2 | Check/document: Python 3.12, Node.js 22+, npm, npx, Docker Desktop, Azure CLI, PowerShell 7, VS Code, Microsoft 365 Agents Toolkit, Copilot developer tenant/license, custom agents and app upload enabled (document manual items; do not automate installs of accounts/licenses/extensions) | **Done** — see `docs/PHASE_0_PREREQUISITES.md` |
| 0.3 | Run `npx -y @microsoft/events-cli status` | **Done** (exit 0) |
| 0.4 | Run `npx -y @microsoft/events-cli sessions --event build-2026 --query "ai agents" --json`; look up a real session with `session <code> --event build-2026 --json` | **Done** (JSON array of 10; `BRK251` lookup OK) |
| 0.5 | Document CLI concepts: `sessions` vs `session`, `--event`, `--query`, `--limit`, `--json`, `MSEVENTS_CACHE_DIR` | **Done** — see `docs/PHASE_0_PREREQUISITES.md` |

**Phase 0 Done when:**
- [x] Python reports version 3.12 (`python3.12` → 3.12.1)
- [x] Node reports version 22 or newer (v22.18.0)
- [x] events-cli status succeeds
- [x] A Build 2026 sessions query returns a JSON array

**Documented gaps (not blocking Phase 0 Done when):** PowerShell 7 missing; VS Code / Agents Toolkit not verified; M365 Copilot tenant/license/custom agents/app upload remain manual.

---

## Phase 1 — Two-Deliverable Model

| ID | Requirement | Status |
|----|-------------|--------|
| 1.1 | Document Component A: Microsoft 365 declarative agent (JSON configuration only) | **Done** — `docs/ARCHITECTURE.md` |
| 1.2 | Document Component B: Python/FastAPI MCP server returning grounded Build sessions | **Done** — `docs/ARCHITECTURE.md` |
| 1.3 | Lock order: build B before A; B independently testable; A is thin config pointing at deployed MCP URL | **Done** — `docs/ARCHITECTURE.md` |

**Phase 1 Done when:** Architecture is clear and B is the next implementation target. **Met.**

---

## Phase 2 — MCP Server (Local)

| ID | Requirement | Status |
|----|-------------|--------|
| 2.1 | Scaffold `conferenceCatalogMCP/` (`__init__.py`, `service.py`, `server.py`, `blob_cache.py`), root `requirements.txt` (fastapi, uvicorn, azure-storage-blob, azure-identity), root `Dockerfile` path present as required by project structure | **Done** |
| 2.2 | Implement `_run_events_cli_json(args)`: locate npx, timeout from `EVENTS_CLI_TIMEOUT_SECONDS` (default 90), parse JSON stdout, raise with stderr on non-zero exit; sole catalog access path | **Done** |
| 2.3 | Normalization contract, transcript resolution order, `whyItMaps` strength bands (High ≥ 0.75, Medium ≥ 0.50, Low &lt; 0.50); missing strings → `none` | **Done** |
| 2.4 | `_score_from_cli_candidate` with formula: `min(1.0, 0.60*overlap + 0.20*exact_phrase + 0.15*title_token_overlap + 0.05*transcript_exists)` | **Done** |
| 2.5 | `match_sessions(signal, limit=3, scheduled_only=False, require_on_demand=True)`: validation, over-fetch `max(limit*3, 10)`, filters, score/sort, shortlist, hydrate shortlist only, return `{signal, results, total, catalogVersion}` | **Done** |
| 2.6 | `get_session_by_code(session_code)`: validation, CLI session lookup, normalize, `{session}`, raise `KeyError` if missing | **Done** |
| 2.7 | FastAPI: `GET /healthz` → `{status: ok}`; `POST /mcp` JSON-RPC: `initialize` (protocolVersion `2024-11-05`, serverInfo.name `conference-catalog-mcp`), `notifications/initialized`, `tools/list` (exactly `match_sessions`, `get_session_by_code`), `tools/call` with `content` + `structuredContent` | **Done** |
| 2.8 | JSON-RPC errors `-32601`, `-32602`, `-32001`, `-32603`; REST `POST /tools/list`, `POST /tools/call` with `NOT_FOUND`, `INVALID_ARGUMENT`, `INTERNAL` | **Done** |
| 2.9 | Local smoke: `python -m uvicorn conferenceCatalogMCP.server:app --host 127.0.0.1 --port 8010`; verify initialize, tools/list, `match_sessions` with signal `agent observability` limit 3; confirm codes via events-cli | **Done** |

**Phase 2 Done when:**
- [x] `initialize` returns `serverInfo.name = conference-catalog-mcp`
- [x] `tools/list` returns exactly `match_sessions` and `get_session_by_code`
- [x] `match_sessions` for `agent observability` returns at most 3 results with `sessionCode`, `recording`, `matchScore`, `whyItMaps`
- [x] Every returned code confirmable via `npx -y @microsoft/events-cli session <code> --event build-2026 --json`

---

## Phase 3 — Two-Tier Cache

| ID | Requirement | Status |
|----|-------------|--------|
| 3.1 | In-process TTL cache | **Done** — `InProcessTTLCache` wired into `match_sessions` / `get_session_by_code` |
| 3.2 | `BlobStorageCache` in `blob_cache.py`: `get(key, ttl)`, `set(key, payload)`, `_created_at` + payload, TTL expiry delete, connection string or DefaultAzureCredential, create container, best-effort failures | **Done** |
| 3.3 | Blob key sanitization: spaces→`_`, `(`→`{`, `)`→`}`, `:`→`-`, max length 1024 | **Done** — `sanitize_blob_key` |
| 3.4 | Wire caches into CatalogService: read in-process → Blob → CLI; write in-process + Blob; env `MCP_CACHE_CONTAINER` (default `mcp-cache`), `MCP_MATCH_CACHE_TTL_SECONDS` (300), `MCP_DETAIL_CACHE_TTL_SECONDS` (900); match/detail key shapes as specified | **Done** |
| 3.5 | Verify Done when: identical signal twice locally; log `Cache HIT`; no CLI on 2nd call | **Done** — signal `agent observability`; 1st call 2 CLI invokes; 2nd call 0 added; `Cache HIT` logged; envelopes equal |

**Phase 3 Done when:** Second identical signal logs `Cache HIT` and skips the events CLI. **Met** (verified 3.5 with live CLI + in-process cache; Blob optional).

---

## Phase 4 — Containerization

| ID | Requirement | Status |
|----|-------------|--------|
| 4.1 | Multi-stage Dockerfile based on `python:3.12-slim`; install nodejs, npm, curl in **final** runtime stage; non-root user; expose 8010; HEALTHCHECK `/healthz`; uvicorn `0.0.0.0:8010` | **Done** — Node 22 via NodeSource in final stage; non-root `appuser`; HEALTHCHECK; port 8010 |
| 4.2 | `docker build -t conferencecatalog-mcp:test .` and `docker run -p 8010:8010 conferencecatalog-mcp:test` | **Done** — image built (Node 22.23.1); container `conferencecatalog-mcp-test` healthy on `0.0.0.0:8010` |
| 4.3 | Smoke from host: `GET /healthz`; `POST /mcp` `match_sessions` returns grounded codes | **Done** — healthz ok; BRK252/ODSP933/DEM361 grounded via CLI |
| 4.4 | Prove npx works inside the running image | **Done** — as `appuser`: npx 10.9.8, Node 22.23.1; `events-cli status` + `sessions` JSON OK |

**Phase 4 Done when:** `/healthz` healthy; `match_sessions` in container returns grounded codes; npx works in final image. **Met.**

---

## Phase 5 — Azure Provisioning

| ID | Requirement | Status |
|----|-------------|--------|
| 5.1 | Resource group | **Done** — `rg-conference-session-advisor` (westus2); user provisioned, agent verified |
| 5.2 | ACR create + `az acr build` image `conferencecatalog-mcp:latest` + show-tags | **Done** — `rmaratheconfacr7672` / `conferencecatalog-mcp:latest` |
| 5.3 | Linux App Service plan B1 + web app custom container | **Done** — `asp-conference-session-advisor` / `rmarathe-conf-advisor-7672` |
| 5.4 | Managed identity `$principalId` (not `$pid`), AcrPull, WEBSITES_PORT=8010 | **Done** — SystemAssigned; AcrPull; setting name present |
| 5.5 | Storage account + blob container `mcp-cache` | **Done** — `rmarathecache7672` / `mcp-cache` |
| 5.6 | Storage Blob Data Contributor on web app identity | **Done** — role name verified on storage scope |
| 5.7 | App settings: `AZURE_STORAGE_ACCOUNT_NAME`, `MCP_CACHE_CONTAINER`, `WEBSITES_PORT` | **Done** — required setting **names** verified (plus TTLs / CLI timeout) |
| 5.8 | Restart; verify public `/healthz`; document log tail + Kudu | **Done** — see `docs/DEPLOYMENT.md` |
| 5.9 | Document security callout: `auth.type = None` is PoC only; real use needs API-key or OAuth (do not implement auth in base project) | **Done** — documented; auth not implemented |

**Phase 5 Done when:** Public `/healthz` ok; repeated signal Cache HIT; managed identity, ACR pull, Blob RBAC work.  
**Status: COMPLETE** — `/healthz` ok; MI + AcrPull + Storage Blob Data Contributor verified; cold→warm live `match_sessions` (~9.8s → ~0.11s, OD812) + Blob cache entries as Cache HIT evidence (literal App Service log line not observed; see `docs/DEPLOYMENT.md`); local pytest **173 passed** (`not real_cli`, ~97% cover).

---

## Phase 6 — Declarative Agent

| ID | Requirement | Status |
|----|-------------|--------|
| 6.1 | `manifest.json` (manifestVersion 1.29, GUID, name, accentColor, icons, declarativeAgents → `declarativeAgent.json`) | **Done** — `app-package/manifest.json` |
| 6.2 | `declarativeAgent.json` (schema v1.7): full workflow instructions, capabilities Email/TeamsMessages/Meetings/OneDriveAndSharePoint/People, four conversation starters, one action → `conferenceCatalogPlugin.json` | **Done** — `app-package/declarativeAgent.json` |
| 6.3 | `conferenceCatalogPlugin.json` (schema v2.4, namespace ConferenceCatalog, grounding text, RemoteMCPServer, auth.type None, spec.url deployed `/mcp`, tools file, run_for_functions) | **Done** — `app-package/conferenceCatalogPlugin.json` → live `/mcp` |
| 6.4 | `conferenceCatalogTools.json` with full input schemas (match_sessions: signal, limit, scheduledOnly, requireOnDemand; get_session_by_code: sessionCode) | **Done** — aligned with server `tools/list` |
| 6.5 | `color.png` 192×192 and `outline.png` 32×32 | **Done** — `app-package/color.png` (192×192 RGB), `app-package/outline.png` (32×32 RGBA) |

**Phase 6 Done when:** All four JSON files validate in Agents Toolkit; `spec.url` points at live deployed `/mcp`.  
**Status: COMPLETE** (package files) — `spec.url` = `https://rmarathe-conf-advisor-7672.azurewebsites.net/mcp`. Agents Toolkit schema validation was **not** run in this environment (manual; covered under Phase 7.1).

---

## Phase 7 — Package and Sideload

| ID | Requirement | Status |
|----|-------------|--------|
| 7.1 | Validate package (Agents Toolkit or Developer Portal) | Not started |
| 7.2 | Zip contents of app-package folder (ZIP root = manifest files and icons, not enclosing folder) | Not started |
| 7.3 | Sideload/provision; open https://m365.cloud.microsoft/chat; run every conversation starter | Not started |

**Phase 7 Done when:** Agent appears in Copilot; Build My Agenda returns agenda grouped by signal with grounded codes and on-demand links.  
**Note:** Manual tenant/license/sideload steps — document required actions; do not claim success unless performed.

---

## Phase 8 — Testing

| ID | Requirement | Status |
|----|-------------|--------|
| 8.1 | L1 unit tests (no network): stub `_run_events_cli_json`; scoring, normalization, `none`, transcript, cache TTL; CatalogService without FastAPI | Not started |
| 8.2 | L2 local server JSON-RPC + grounded integration; verify codes via CLI | Not started |
| 8.3 | L3 container tests | Not started |
| 8.4 | L4 deployed App Service tests | Not started |
| 8.5 | Required JSON-RPC expectations (initialize, tools/list, match_sessions signal `end-to-end observability for ai agents`, get_session_by_code real + unknown) | Not started |
| 8.6 | Negative tests: empty signal, invalid limit, irrelevant signal, on-demand default | Not started |
| 8.7 | Agent tests E1–E6 | Not started |
| 8.8 | Grounding pass: every sessionCode confirmable via events-cli; no invented sessions | Not started |

---

## Phase 9 — Definition of Done

| ID | Requirement | Status |
|----|-------------|--------|
| 9.1 | `match_sessions` returns grounded, on-demand sessions with codes and links | Not started |
| 9.2 | `get_session_by_code` returns full metadata or clean not-found | Not started |
| 9.3 | Agent groups results by signal | Not started |
| 9.4 | Groups ordered by signal importance | Not started |
| 9.5 | Agent does not invent sessions | Not started |
| 9.6 | MCP server deployed | Not started |
| 9.7 | `GET /healthz` healthy | Not started |
| 9.8 | Repeated identical queries produce Cache HIT | Not started |
| 9.9 | App package validates | Not started |
| 9.10 | App package sideloads | Not started |
| 9.11 | Every conversation starter behaves as required in Phase 8 | Not started |
| 9.12 | Document production requirement: add `/mcp` authentication before real use (`auth.type=None` is PoC only; do not implement custom auth in base project) | Not started |

Also required in project documentation (not product integrations): market comparison (Grip, Glue Up, Sessionboard, Inference Systems, CrowdComms) and key differentiators per contract §6.

---

## Success criteria (track across phases)

| ID | Criterion | Status |
|----|-----------|--------|
| SC-1 | Agenda grouped by signal, ordered by importance; code + rationale + link | Not started |
| SC-2 | No invented sessions; codes exist in Build catalog | Not started |
| SC-3 | Up to 3 matches; first strongest; matchScore ordering | Not started |
| SC-4 | Default on-demand; recording ≠ `none` when required | Not started |
| SC-5 | No grounded match → say so, do not guess | Not started |
| SC-6 | No enterprise context → `No enterprise data found.` | Not started |
| SC-7 | `GET /healthz` → HTTP 200 | Not started |
| SC-8 | Repeated identical queries → log `Cache HIT` | Not started |

---

## Next action

Phase 6 package complete. Proceed to **Phase 7** (Agents Toolkit validate → zip `app-package` contents → sideload → run conversation starters).
