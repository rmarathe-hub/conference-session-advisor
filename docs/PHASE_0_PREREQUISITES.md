# Phase 0 — Prerequisites

Verified on **2026-07-12** against the Conference Session Advisor design contract.

Use **`python3.12`** for this project (not the default `python3`, which may be a newer major).

---

## Automated / local tool checks

| Prerequisite | Required | Result | Notes |
|--------------|----------|--------|-------|
| Python 3.12 | 3.12 | **Pass** — `Python 3.12.1` via `/usr/local/bin/python3.12` | Also present under Frameworks. Default `python3` → 3.14.6; Anaconda `python` → 3.11.5. Prefer `python3.12`. |
| Node.js | 22+ | **Pass** — `v22.18.0` (`/usr/local/bin/node`) | |
| npm | present | **Pass** — `10.9.3` | |
| npx | present | **Pass** — `10.9.3` | |
| Docker Desktop | present | **Pass** — Docker 29.1.2; `Docker.app` present; daemon running | |
| Azure CLI | present | **Pass** — `azure-cli 2.87.0` (`/opt/homebrew/bin/az`) | Ensure `/opt/homebrew/bin` is on PATH in shells used for Phase 5. |
| PowerShell 7 | present | **Missing** | `pwsh` not on PATH. Install PowerShell 7 before Phase 5 Azure commands that are PowerShell-oriented. Azure CLI `az` still works from zsh/bash. |
| Visual Studio Code | present | **Missing as VS Code.app** | `Cursor.app` is installed. Contract lists VS Code + Microsoft 365 Agents Toolkit; install VS Code (or confirm Toolkit workflow in an allowed host) before Phase 6–7 validation/sideload. |
| Microsoft 365 Agents Toolkit | VS Code extension | **Not verified** | Could not list extensions (VS Code CLI/app absent). Install in VS Code before Phase 6 validation. |

### Commands run

```text
python3.12 --version
# Python 3.12.1

node --version
# v22.18.0

npx -y @microsoft/events-cli status
# build-2025 / ignite-2025 / build-2026 cache status reported (exit 0)

npx -y @microsoft/events-cli sessions --event build-2026 --query "ai agents" --json
# JSON array length 10 (CLI fetched Microsoft Build 2026: 461 sessions)

npx -y @microsoft/events-cli session BRK251 --event build-2026 --json
# sessionCode BRK251; hasOnDemand true; title present
```

---

## Manual Microsoft 365 prerequisites (not automated)

Do **not** automate installation of accounts, licenses, tenant settings, or editor extensions.

| Prerequisite | Status | Action required from you |
|--------------|--------|---------------------------|
| Microsoft 365 Copilot developer tenant | Manual | Confirm you have a suitable tenant. |
| Microsoft 365 Copilot license | Manual | Confirm license on the account used for sideload/chat. |
| Custom agents enabled | Manual | Enable in tenant / admin settings as required by Copilot extensibility. |
| Custom app upload or integrated apps enabled | Manual | Required for Phase 7 sideload. |
| Microsoft 365 Agents Toolkit in VS Code | Manual | Install after VS Code is available; validate agent JSON in Phase 6. |

---

## events-cli verification (0.3 / 0.4)

### Status (0.3)

`npx -y @microsoft/events-cli status` succeeded (exit 0). Reported cache lines for `build-2025`, `ignite-2025`, and `build-2026`.

### Sessions search (0.4)

```bash
npx -y @microsoft/events-cli sessions --event build-2026 --query "ai agents" --json
```

- Returned a **JSON array** (10 objects for this query).
- Sample fields observed: `sessionCode`, `title`, `description`, `speakers`, `timeSlot`, `startDateTime`, `endDateTime`, `location`, `level`, `type`, `topic`, `solutionArea`, `product`, `languages`, `tags`, `deliveryTypes`, `viewingOptions`, `hasLiveStream`, `hasOnDemand`, `relatedSessionCodes`, `slideDeck`, `onDemand`, `event`.
- First sample code: **BRK251**.

### Direct session lookup (0.4)

```bash
npx -y @microsoft/events-cli session BRK251 --event build-2026 --json
```

- Returned a JSON **object** for BRK251.
- `hasOnDemand`: true  
- `onDemand`: Medius embed URL present  
- Title: Build secure and enterprise-ready agents with Agent 365  

---

## CLI concepts (0.5)

| Concept | Meaning for this project |
|---------|---------------------------|
| `sessions` | Search/list command. Returns multiple catalog hits for a query against an event. Used by `match_sessions` over-fetch. |
| `session` | Single-session lookup by authoritative session code. Used for hydration and `get_session_by_code`. |
| `--event` | Event slug. This project uses **`build-2026` only** (spell exactly). |
| `--query` | Free-text search string for `sessions` (e.g. a customer signal). |
| `--limit` | Caps how many sessions the CLI returns for a search. CatalogService over-fetches with `max(limit * 3, 10)`. |
| `--json` | Machine-readable JSON on stdout. `_run_events_cli_json` must parse this; do not scrape human text. |
| `MSEVENTS_CACHE_DIR` | Optional env var controlling where `@microsoft/events-cli` stores its on-disk event session cache. Distinct from the MCP server’s in-process / Azure Blob caches (Phase 3). |

### Authoritative access rule (later Phase 2)

All catalog reads in the MCP server must go through `_run_events_cli_json(args)` invoking:

```bash
npx -y @microsoft/events-cli <args>
```

No alternate catalog sources or static session datasets.

---

## Phase 0 Done when

| Condition | Met? |
|-----------|------|
| Python reports version 3.12 | **Yes** (`python3.12` → 3.12.1) |
| Node reports version 22 or newer | **Yes** (v22.18.0) |
| events-cli status succeeds | **Yes** |
| Build 2026 sessions query returns a JSON array | **Yes** |

### Gaps before later phases (documented, not blocking Phase 0 Done when)

1. Install **PowerShell 7** (`pwsh`) for PowerShell-oriented Azure provisioning steps in Phase 5 (or run the equivalent `az` commands from zsh).
2. Install **Visual Studio Code** and the **Microsoft 365 Agents Toolkit** extension before Phase 6–7 validation and sideload.
3. Confirm **Copilot tenant, license, custom agents, and custom app upload / integrated apps** before Phase 7.

### If it breaks (from contract)

- If `npx` is not found: install Node.js, confirm PATH, reopen terminal.
- If a broad query returns empty JSON: confirm `build-2026` is spelled exactly.

---

## Next action

Proceed to **Phase 1** (two-deliverable model documentation), then Phase 2 MCP server implementation.
