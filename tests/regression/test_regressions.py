"""Robustness and regression tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from conferenceCatalogMCP.service import CatalogService


def test_subprocess_never_shell_true(svc: CatalogService, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "conferenceCatalogMCP.service.shutil.which", lambda _: "/bin/npx"
    )
    run = MagicMock(return_value=MagicMock(returncode=0, stdout="[]", stderr=""))
    monkeypatch.setattr("conferenceCatalogMCP.service.subprocess.run", run)
    svc._run_events_cli_json(["sessions", "--query", "a;b", "--json"])
    assert run.call_args.kwargs.get("shell") in (None, False)


def test_null_params_on_tools_call_via_handler():
    from conferenceCatalogMCP.server import _handle_json_rpc

    # params null becomes {}
    out = _handle_json_rpc(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": None}
    )
    assert "result" in out
    assert len(out["result"]["tools"]) == 2


def test_array_params_tools_call_errors():
    from conferenceCatalogMCP.server import _handle_json_rpc

    out = _handle_json_rpc(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": ["match_sessions"],
        }
    )
    # list has no .get — becomes internal or invalid
    assert "error" in out
    assert out["error"]["code"] in (-32602, -32603)


def test_extra_fields_ignored_in_match(svc: CatalogService, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(svc, "_run_events_cli_json", MagicMock(return_value=[]))
    out = svc.match_sessions("agents", limit=1)
    assert out["results"] == []


def test_regression_limit_bool_rejected(svc: CatalogService):
    """bool is a subclass of int in Python; must still be rejected."""
    with pytest.raises(ValueError):
        svc.match_sessions("agents", limit=True)


def test_regression_coerce_nested_sessions_key(svc: CatalogService):
    payload = {"sessions": [{"sessionCode": "N1", "title": "Nested"}]}
    assert svc._coerce_session_list(payload)[0]["sessionCode"] == "N1"


def test_regression_coerce_malformed_ignored(svc: CatalogService):
    assert svc._coerce_session_list([1, "x", None, {"sessionCode": "OK"}]) == [
        {"sessionCode": "OK"}
    ]
