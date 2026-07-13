"""Unit tests for _run_events_cli_json."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock

import pytest

from conferenceCatalogMCP.service import CatalogService, EventsCliError


def test_missing_npx_raises(svc: CatalogService, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("conferenceCatalogMCP.service.shutil.which", lambda _: None)
    with pytest.raises(EventsCliError, match="npx was not found"):
        svc._run_events_cli_json(["status"])


def test_command_uses_argument_list_not_shell(
    svc: CatalogService, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        "conferenceCatalogMCP.service.shutil.which", lambda _: "/usr/bin/npx"
    )
    completed = MagicMock(
        returncode=0, stdout='{"ok": true}', stderr=""
    )
    run = MagicMock(return_value=completed)
    monkeypatch.setattr("conferenceCatalogMCP.service.subprocess.run", run)

    result = svc._run_events_cli_json(["sessions", "--event", "build-2026", "--json"])
    assert result == {"ok": True}
    args, kwargs = run.call_args
    cmd = args[0]
    assert cmd[0] == "/usr/bin/npx"
    assert cmd[1:3] == ["-y", "@microsoft/events-cli"]
    assert cmd[3:] == ["sessions", "--event", "build-2026", "--json"]
    assert kwargs.get("shell") is not True
    assert kwargs.get("capture_output") is True
    assert kwargs.get("text") is True
    assert kwargs.get("check") is False


@pytest.mark.parametrize(
    "env_value,expected_timeout",
    [
        (None, 90),
        ("120", 120),
        ("30", 30),
    ],
)
def test_timeout_default_and_override(
    svc: CatalogService,
    monkeypatch: pytest.MonkeyPatch,
    env_value: str | None,
    expected_timeout: int,
):
    monkeypatch.setattr(
        "conferenceCatalogMCP.service.shutil.which", lambda _: "/usr/bin/npx"
    )
    if env_value is None:
        monkeypatch.delenv("EVENTS_CLI_TIMEOUT_SECONDS", raising=False)
    else:
        monkeypatch.setenv("EVENTS_CLI_TIMEOUT_SECONDS", env_value)
    completed = MagicMock(returncode=0, stdout="[]", stderr="")
    run = MagicMock(return_value=completed)
    monkeypatch.setattr("conferenceCatalogMCP.service.subprocess.run", run)
    svc._run_events_cli_json(["status"])
    assert run.call_args.kwargs["timeout"] == expected_timeout


@pytest.mark.parametrize(
    "stdout,expected",
    [
        ("[]", []),
        ('{"a": 1}', {"a": 1}),
        ('[{"sessionCode": "X"}]', [{"sessionCode": "X"}]),
    ],
)
def test_parses_valid_json(
    svc: CatalogService,
    monkeypatch: pytest.MonkeyPatch,
    stdout: str,
    expected,
):
    monkeypatch.setattr(
        "conferenceCatalogMCP.service.shutil.which", lambda _: "/usr/bin/npx"
    )
    monkeypatch.setattr(
        "conferenceCatalogMCP.service.subprocess.run",
        MagicMock(return_value=MagicMock(returncode=0, stdout=stdout, stderr="")),
    )
    assert svc._run_events_cli_json(["x"]) == expected


def test_malformed_json_raises(svc: CatalogService, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "conferenceCatalogMCP.service.shutil.which", lambda _: "/usr/bin/npx"
    )
    monkeypatch.setattr(
        "conferenceCatalogMCP.service.subprocess.run",
        MagicMock(return_value=MagicMock(returncode=0, stdout="not-json", stderr="")),
    )
    with pytest.raises(EventsCliError, match="not valid JSON"):
        svc._run_events_cli_json(["x"])


def test_empty_stdout_raises(svc: CatalogService, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "conferenceCatalogMCP.service.shutil.which", lambda _: "/usr/bin/npx"
    )
    monkeypatch.setattr(
        "conferenceCatalogMCP.service.subprocess.run",
        MagicMock(return_value=MagicMock(returncode=0, stdout="  \n", stderr="")),
    )
    with pytest.raises(EventsCliError, match="empty stdout"):
        svc._run_events_cli_json(["x"])


def test_nonzero_exit_includes_stderr(
    svc: CatalogService, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        "conferenceCatalogMCP.service.shutil.which", lambda _: "/usr/bin/npx"
    )
    monkeypatch.setattr(
        "conferenceCatalogMCP.service.subprocess.run",
        MagicMock(
            return_value=MagicMock(
                returncode=7, stdout="", stderr="boom failure details"
            )
        ),
    )
    with pytest.raises(EventsCliError, match="boom failure details") as exc:
        svc._run_events_cli_json(["x"])
    assert "7" in str(exc.value)


def test_timeout_raises(svc: CatalogService, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "conferenceCatalogMCP.service.shutil.which", lambda _: "/usr/bin/npx"
    )
    monkeypatch.delenv("EVENTS_CLI_TIMEOUT_SECONDS", raising=False)

    def _raise(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="npx", timeout=90)

    monkeypatch.setattr("conferenceCatalogMCP.service.subprocess.run", _raise)
    with pytest.raises(EventsCliError, match="timed out"):
        svc._run_events_cli_json(["x"])


def test_catalog_reads_go_through_wrapper_only(svc: CatalogService, monkeypatch):
    """match_sessions and get_session_by_code must call _run_events_cli_json."""
    calls = []

    def fake(args):
        calls.append(list(args))
        if args[0] == "sessions":
            return []
        return {"sessionCode": "Z", "title": "z"}

    monkeypatch.setattr(svc, "_run_events_cli_json", fake)
    svc.match_sessions("agents", limit=1, require_on_demand=False)
    assert any(c[0] == "sessions" for c in calls)
    svc.get_session_by_code("Z")
    assert any(c[0] == "session" and c[1] == "Z" for c in calls)
