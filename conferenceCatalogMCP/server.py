"""FastAPI MCP server for grounded Microsoft Build session matching."""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from conferenceCatalogMCP.service import CatalogService

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "conference-catalog-mcp"

app = FastAPI(title=SERVER_NAME)
catalog_service = CatalogService()


def _json_rpc_result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _json_rpc_error(
    request_id: Any, code: int, message: str, data: Any = None
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def _tool_result(payload: Any) -> dict[str, Any]:
    text = json.dumps(payload, indent=2, default=str)
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": payload,
    }


def _tools_list_payload() -> dict[str, Any]:
    return {
        "tools": [
            {
                "name": "match_sessions",
                "description": (
                    "Match a customer or priority signal to grounded Microsoft "
                    "Build 2026 sessions. Returns up to `limit` on-demand sessions "
                    "by default, strongest first."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "signal": {
                            "type": "string",
                            "description": "Atomic priority, challenge, initiative, or pain point.",
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 10,
                            "default": 3,
                            "description": "Maximum sessions to return (1-10).",
                        },
                        "scheduledOnly": {
                            "type": "boolean",
                            "default": False,
                            "description": "When true, keep only sessions with schedule times.",
                        },
                        "requireOnDemand": {
                            "type": "boolean",
                            "default": True,
                            "description": "When true, keep only sessions with on-demand recordings.",
                        },
                    },
                    "required": ["signal"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "get_session_by_code",
                "description": (
                    "Return full normalized metadata for one Build 2026 session "
                    "code from the authoritative events-cli catalog."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "sessionCode": {
                            "type": "string",
                            "description": "Authoritative Microsoft Build session code.",
                        }
                    },
                    "required": ["sessionCode"],
                    "additionalProperties": False,
                },
            },
        ]
    }


def _dispatch_tool(name: str, arguments: dict[str, Any] | None) -> Any:
    args = arguments or {}
    if name == "match_sessions":
        return catalog_service.match_sessions(
            signal=args.get("signal"),
            limit=args.get("limit", 3),
            scheduled_only=bool(args.get("scheduledOnly", False)),
            require_on_demand=bool(args.get("requireOnDemand", True)),
        )
    if name == "get_session_by_code":
        return catalog_service.get_session_by_code(args.get("sessionCode"))
    raise KeyError(name)


def _handle_initialize(params: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {"tools": {}},
        "serverInfo": {"name": SERVER_NAME, "version": "1.0.0"},
    }


def _handle_json_rpc(body: dict[str, Any]) -> dict[str, Any] | None:
    """Handle one JSON-RPC request object. Returns None for notifications without id."""
    request_id = body.get("id")
    method = body.get("method")
    params = body.get("params") or {}

    if not method:
        return _json_rpc_error(request_id, -32600, "Invalid Request: method required")

    try:
        if method == "initialize":
            return _json_rpc_result(request_id, _handle_initialize(params))

        if method == "notifications/initialized":
            # Notification may omit id; return empty successful result when id present.
            if request_id is None:
                return None
            return _json_rpc_result(request_id, {})

        if method == "tools/list":
            return _json_rpc_result(request_id, _tools_list_payload())

        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if not name:
                raise ValueError("tools/call requires params.name")
            if name not in {"match_sessions", "get_session_by_code"}:
                return _json_rpc_error(
                    request_id, -32601, f"Unknown tool: {name}"
                )
            payload = _dispatch_tool(name, arguments)
            return _json_rpc_result(request_id, _tool_result(payload))

        return _json_rpc_error(request_id, -32601, f"Method not found: {method}")

    except ValueError as exc:
        return _json_rpc_error(request_id, -32602, str(exc))
    except KeyError as exc:
        return _json_rpc_error(
            request_id, -32001, f"Not found: {exc}", data={"key": str(exc)}
        )
    except Exception as exc:  # noqa: BLE001 — map all other errors to -32603
        return _json_rpc_error(request_id, -32603, str(exc))


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/mcp")
async def mcp_endpoint(request: Request):
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse(
            _json_rpc_error(None, -32600, "Invalid JSON body"), status_code=400
        )

    if isinstance(body, list):
        responses = []
        for item in body:
            if not isinstance(item, dict):
                responses.append(
                    _json_rpc_error(None, -32600, "Invalid Request in batch")
                )
                continue
            response = _handle_json_rpc(item)
            if response is not None:
                responses.append(response)
        return JSONResponse(responses)

    if not isinstance(body, dict):
        return JSONResponse(
            _json_rpc_error(None, -32600, "Invalid Request"), status_code=400
        )

    response = _handle_json_rpc(body)
    if response is None:
        return JSONResponse({})
    return JSONResponse(response)


@app.post("/tools/list")
async def tools_list_rest():
    return JSONResponse(_tools_list_payload())


@app.post("/tools/call")
async def tools_call_rest(request: Request):
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse(
            {"error": "INVALID_ARGUMENT", "message": "Invalid JSON body"},
            status_code=400,
        )

    if not isinstance(body, dict):
        return JSONResponse(
            {"error": "INVALID_ARGUMENT", "message": "Body must be a JSON object"},
            status_code=400,
        )

    name = body.get("name") or body.get("tool")
    arguments = body.get("arguments") or body.get("params") or {}
    if not name:
        return JSONResponse(
            {"error": "INVALID_ARGUMENT", "message": "name is required"},
            status_code=400,
        )

    try:
        if name not in {"match_sessions", "get_session_by_code"}:
            return JSONResponse(
                {"error": "NOT_FOUND", "message": f"Unknown tool: {name}"},
                status_code=404,
            )
        payload = _dispatch_tool(name, arguments)
        return JSONResponse(_tool_result(payload))
    except ValueError as exc:
        return JSONResponse(
            {"error": "INVALID_ARGUMENT", "message": str(exc)},
            status_code=400,
        )
    except KeyError as exc:
        return JSONResponse(
            {"error": "NOT_FOUND", "message": f"Not found: {exc}"},
            status_code=404,
        )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            {"error": "INTERNAL", "message": str(exc)},
            status_code=500,
        )
