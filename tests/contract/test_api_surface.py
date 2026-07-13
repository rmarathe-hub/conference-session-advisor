"""FastAPI / MCP / REST contract tests."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from conferenceCatalogMCP import server as server_module
from conferenceCatalogMCP.service import CatalogService, EventsCliError
from tests.conftest import load_fixture, make_cli_router

BUSINESS_ROUTES = {
    ("GET", "/healthz"),
    ("POST", "/mcp"),
    ("POST", "/tools/list"),
    ("POST", "/tools/call"),
}


def test_healthz(client: TestClient):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_initialize(client: TestClient):
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    body = resp.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 1
    assert body["result"]["protocolVersion"] == "2024-11-05"
    assert body["result"]["serverInfo"]["name"] == "conference-catalog-mcp"


def test_notifications_initialized_without_id(client: TestClient):
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
    )
    assert resp.status_code == 200
    assert resp.json() == {}


def test_notifications_initialized_with_id(client: TestClient):
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 9,
            "method": "notifications/initialized",
            "params": {},
        },
    )
    assert resp.json() == {"jsonrpc": "2.0", "id": 9, "result": {}}


def test_tools_list_exactly_two(client: TestClient):
    resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = resp.json()["result"]["tools"]
    names = [t["name"] for t in tools]
    assert names == ["match_sessions", "get_session_by_code"]
    assert len(tools) == 2

    match = tools[0]
    assert "signal" in match["inputSchema"]["required"]
    props = match["inputSchema"]["properties"]
    assert props["limit"]["default"] == 3
    assert props["limit"]["minimum"] == 1
    assert props["limit"]["maximum"] == 10
    assert props["scheduledOnly"]["default"] is False
    assert props["requireOnDemand"]["default"] is True
    assert tools[1]["inputSchema"]["required"] == ["sessionCode"]
    for tool in tools:
        assert tool["description"]
        assert isinstance(tool["inputSchema"], dict)


def test_no_third_tool_regression(client: TestClient):
    tools = client.post(
        "/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    ).json()["result"]["tools"]
    assert len(tools) == 2


def test_tools_call_match_sessions_shape(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    search = load_fixture("search_mixed.json")
    service = CatalogService()
    monkeypatch.setattr(service, "_run_events_cli_json", make_cli_router(search))
    monkeypatch.setattr(server_module, "catalog_service", service)

    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "match_sessions",
                "arguments": {"signal": "agent observability", "limit": 3},
            },
        },
    )
    result = resp.json()["result"]
    assert set(result.keys()) == {"content", "structuredContent"}
    assert isinstance(result["content"], list)
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "text"
    parsed = json.loads(result["content"][0]["text"])
    assert parsed == result["structuredContent"]
    assert "results" in parsed
    assert len(parsed["results"]) <= 3


def test_tools_call_get_session(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    service = CatalogService()
    monkeypatch.setattr(
        service,
        "_run_events_cli_json",
        MagicMock(return_value=load_fixture("session_complete.json")),
    )
    monkeypatch.setattr(server_module, "catalog_service", service)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "get_session_by_code",
                "arguments": {"sessionCode": "BRK100"},
            },
        },
    )
    sc = resp.json()["result"]["structuredContent"]
    assert sc["session"]["sessionCode"] == "BRK100"


@pytest.mark.parametrize(
    "payload,code",
    [
        ({"jsonrpc": "2.0", "id": 1, "method": "nope"}, -32601),
        (
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "match_sessions", "arguments": {"signal": ""}},
            },
            -32602,
        ),
        (
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "get_session_by_code",
                    "arguments": {"sessionCode": "NOPE"},
                },
            },
            -32001,
        ),
        (
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "unknown_tool", "arguments": {}},
            },
            -32601,
        ),
    ],
)
def test_jsonrpc_error_codes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, payload, code
):
    service = CatalogService()
    monkeypatch.setattr(service, "_run_events_cli_json", MagicMock(return_value=[]))
    monkeypatch.setattr(server_module, "catalog_service", service)
    resp = client.post("/mcp", json=payload)
    body = resp.json()
    assert body["id"] == payload["id"]
    assert body["error"]["code"] == code
    assert "traceback" not in json.dumps(body).lower()


def test_internal_error_maps_to_32603(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    service = CatalogService()

    def boom(_args):
        raise EventsCliError("simulated failure")

    monkeypatch.setattr(service, "_run_events_cli_json", boom)
    monkeypatch.setattr(server_module, "catalog_service", service)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 99,
            "method": "tools/call",
            "params": {
                "name": "match_sessions",
                "arguments": {"signal": "agents", "limit": 1},
            },
        },
    )
    assert resp.json()["error"]["code"] == -32603


def test_rest_tools_list(client: TestClient):
    resp = client.post("/tools/list")
    names = [t["name"] for t in resp.json()["tools"]]
    assert names == ["match_sessions", "get_session_by_code"]


def test_rest_tools_call_success(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    service = CatalogService()
    monkeypatch.setattr(
        service,
        "_run_events_cli_json",
        make_cli_router(load_fixture("search_mixed.json")),
    )
    monkeypatch.setattr(server_module, "catalog_service", service)
    resp = client.post(
        "/tools/call",
        json={"name": "match_sessions", "arguments": {"signal": "agents", "limit": 2}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "structuredContent" in body
    assert body["content"][0]["type"] == "text"


@pytest.mark.parametrize(
    "body,error",
    [
        ({"name": "match_sessions", "arguments": {"signal": ""}}, "INVALID_ARGUMENT"),
        ({"name": "nope", "arguments": {}}, "NOT_FOUND"),
        (
            {"name": "get_session_by_code", "arguments": {"sessionCode": "NOPE"}},
            "NOT_FOUND",
        ),
        ({}, "INVALID_ARGUMENT"),
    ],
)
def test_rest_error_strings(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, body, error
):
    service = CatalogService()
    monkeypatch.setattr(service, "_run_events_cli_json", MagicMock(return_value=[]))
    monkeypatch.setattr(server_module, "catalog_service", service)
    resp = client.post("/tools/call", json=body)
    assert resp.json()["error"] == error


def test_rest_malformed_json(client: TestClient):
    resp = client.post(
        "/tools/call",
        content=b"not-json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.json()["error"] == "INVALID_ARGUMENT"


def test_rest_internal(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    service = CatalogService()
    monkeypatch.setattr(
        service,
        "_run_events_cli_json",
        MagicMock(side_effect=EventsCliError("boom")),
    )
    monkeypatch.setattr(server_module, "catalog_service", service)
    resp = client.post(
        "/tools/call",
        json={"name": "match_sessions", "arguments": {"signal": "x", "limit": 1}},
    )
    assert resp.json()["error"] == "INTERNAL"


def test_business_routes_only():
    routes = {
        (list(r.methods)[0], r.path)
        for r in server_module.app.routes
        if hasattr(r, "methods") and getattr(r, "path", None) in {
            "/healthz",
            "/mcp",
            "/tools/list",
            "/tools/call",
            "/docs",
            "/openapi.json",
            "/redoc",
        }
    }
    business = {(m, p) for m, p in routes if p in {"/healthz", "/mcp", "/tools/list", "/tools/call"}}
    assert business == BUSINESS_ROUTES


def test_mcp_malformed_json(client: TestClient):
    resp = client.post(
        "/mcp", content=b"{bad", headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == -32600


@pytest.mark.parametrize(
    "signal",
    [
        'agents; rm -rf /',
        'agents" && echo',
        "agents\nOR 1=1",
        "agents' OR '1'='1",
        "代理 observability",
        "a" * 5000,
    ],
)
def test_metacharacters_passed_as_argv(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, signal: str
):
    captured = []

    def fake(args):
        captured.append(list(args))
        return []

    service = CatalogService()
    monkeypatch.setattr(service, "_run_events_cli_json", fake)
    monkeypatch.setattr(server_module, "catalog_service", service)
    client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "match_sessions",
                "arguments": {"signal": signal, "limit": 1},
            },
        },
    )
    assert captured
    assert captured[0][0] == "sessions"
    assert signal.strip() == captured[0][captured[0].index("--query") + 1]


def test_determinism_repeated_requests(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    service = CatalogService()
    monkeypatch.setattr(
        service,
        "_run_events_cli_json",
        make_cli_router(load_fixture("search_mixed.json")),
    )
    monkeypatch.setattr(server_module, "catalog_service", service)
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "match_sessions",
            "arguments": {"signal": "agent observability", "limit": 3},
        },
    }
    bodies = [client.post("/mcp", json=payload).json()["result"]["structuredContent"] for _ in range(5)]
    assert all(b == bodies[0] for b in bodies)
