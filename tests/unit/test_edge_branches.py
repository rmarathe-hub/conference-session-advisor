"""Extra branch coverage for service and server edge paths."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from conferenceCatalogMCP import server as server_module
from conferenceCatalogMCP.service import CatalogService
from conferenceCatalogMCP.server import _dispatch_tool, _handle_json_rpc


def test_as_none_string_non_string(svc: CatalogService):
    assert svc._as_none_string(42) == "42"
    assert svc._as_none_string(0) == "0"


def test_normalize_rejects_non_dict(svc: CatalogService):
    with pytest.raises(TypeError):
        svc._normalize_session(["not", "a", "dict"])  # type: ignore[arg-type]


def test_has_on_demand_false_flag_but_url(svc: CatalogService):
    candidate = {
        "hasOnDemand": False,
        "onDemand": "https://medius.microsoft.com/Embed/video-nc/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    }
    assert svc._has_on_demand(candidate) is True


def test_has_on_demand_false_flag_no_url(svc: CatalogService):
    assert svc._has_on_demand({"hasOnDemand": False}) is False


def test_has_on_demand_missing_flag_uses_url(svc: CatalogService):
    assert (
        svc._has_on_demand(
            {
                "onDemand": "https://medius.microsoft.com/Embed/video-nc/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
            }
        )
        is True
    )
    assert svc._has_on_demand({"title": "x"}) is False


def test_coerce_none(svc: CatalogService):
    assert svc._coerce_session_list(None) == []


def test_merge_skips_none_and_blank(svc: CatalogService):
    merged = svc._merge_candidate(
        {"sessionCode": "A", "title": "Keep"},
        {"title": None, "description": "  ", "slideDeck": "deck"},
    )
    assert merged["title"] == "Keep"
    assert "description" not in merged or merged.get("description") != "  "
    assert merged["slideDeck"] == "deck"


def test_match_sessions_code_none_skips_hydration(
    svc: CatalogService, monkeypatch: pytest.MonkeyPatch
):
    search = [
        {
            "title": "agent observability",
            "description": "agent observability",
            "onDemand": "https://medius.microsoft.com/Embed/video-nc/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "hasOnDemand": True,
        }
    ]
    calls = []

    def router(args):
        calls.append(list(args))
        if args[0] == "sessions":
            return search
        raise AssertionError("should not hydrate")

    monkeypatch.setattr(svc, "_run_events_cli_json", router)
    out = svc.match_sessions("agent observability", limit=1)
    assert out["results"][0]["sessionCode"] == "none"
    assert not any(c[0] == "session" for c in calls)


def test_get_session_code_field_none(svc: CatalogService, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        svc,
        "_run_events_cli_json",
        MagicMock(return_value={"sessions": [{"title": "No code here"}]}),
    )
    with pytest.raises(KeyError):
        svc.get_session_by_code("X")


def test_get_session_literal_none_code(svc: CatalogService, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        svc,
        "_run_events_cli_json",
        MagicMock(return_value={"sessionCode": "none", "title": "x"}),
    )
    with pytest.raises(KeyError):
        svc.get_session_by_code("none")


def test_dispatch_unknown_tool_keyerror():
    with pytest.raises(KeyError):
        _dispatch_tool("nope", {})


def test_missing_method():
    out = _handle_json_rpc({"jsonrpc": "2.0", "id": 1})
    assert out["error"]["code"] == -32600


def test_tools_call_missing_name():
    out = _handle_json_rpc(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"arguments": {}},
        }
    )
    assert out["error"]["code"] == -32602


def test_batch_jsonrpc(client: TestClient):
    resp = client.post(
        "/mcp",
        json=[
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            "bad",
        ],
    )
    body = resp.json()
    assert isinstance(body, list)
    assert body[0]["result"]["serverInfo"]["name"] == "conference-catalog-mcp"
    assert any(item.get("error", {}).get("code") == -32600 for item in body if isinstance(item, dict))


def test_mcp_non_object_body(client: TestClient):
    resp = client.post("/mcp", json=42)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == -32600


def test_rest_non_object_body(client: TestClient):
    resp = client.post("/tools/call", json=[1, 2, 3])
    assert resp.json()["error"] == "INVALID_ARGUMENT"
