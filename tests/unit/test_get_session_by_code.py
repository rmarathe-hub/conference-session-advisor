"""get_session_by_code contract tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from conferenceCatalogMCP.service import CatalogService
from tests.conftest import REQUIRED_SESSION_FIELDS, load_fixture


@pytest.mark.parametrize("code", ["", "   ", None])
def test_rejects_empty_code(svc: CatalogService, code):
    with pytest.raises(ValueError, match="session_code"):
        svc.get_session_by_code(code)  # type: ignore[arg-type]


def test_valid_session(svc: CatalogService, monkeypatch: pytest.MonkeyPatch):
    detail = load_fixture("session_complete.json")
    monkeypatch.setattr(svc, "_run_events_cli_json", MagicMock(return_value=detail))
    out = svc.get_session_by_code("BRK100")
    assert set(out.keys()) == {"session"}
    session = out["session"]
    for field in REQUIRED_SESSION_FIELDS:
        assert field in session
    assert session["sessionCode"] == "BRK100"
    assert session["recording"] != "none"


def test_strips_whitespace_code(svc: CatalogService, monkeypatch: pytest.MonkeyPatch):
    mock = MagicMock(return_value=load_fixture("session_complete.json"))
    monkeypatch.setattr(svc, "_run_events_cli_json", mock)
    svc.get_session_by_code("  BRK100  ")
    args = mock.call_args.args[0]
    assert args == ["session", "BRK100", "--event", "build-2026", "--json"]


def test_unknown_empty_list(svc: CatalogService, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(svc, "_run_events_cli_json", MagicMock(return_value=[]))
    with pytest.raises(KeyError):
        svc.get_session_by_code("MISSING")


def test_unknown_empty_object(svc: CatalogService, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(svc, "_run_events_cli_json", MagicMock(return_value={}))
    with pytest.raises(KeyError):
        svc.get_session_by_code("MISSING")


def test_object_without_code_raises(svc: CatalogService, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        svc, "_run_events_cli_json", MagicMock(return_value={"title": "No code"})
    )
    with pytest.raises(KeyError):
        svc.get_session_by_code("MISSING")


def test_list_response(svc: CatalogService, monkeypatch: pytest.MonkeyPatch):
    detail = load_fixture("session_complete.json")
    monkeypatch.setattr(svc, "_run_events_cli_json", MagicMock(return_value=[detail]))
    out = svc.get_session_by_code("BRK100")
    assert out["session"]["sessionCode"] == "BRK100"


def test_partial_detail_normalized(svc: CatalogService, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        svc,
        "_run_events_cli_json",
        MagicMock(return_value={"sessionCode": "P1", "title": "Partial"}),
    )
    session = svc.get_session_by_code("P1")["session"]
    assert session["capability"] == "none"
    assert session["recording"] == "none"
    assert session["transcript"] == "none"
    assert isinstance(session["matchScore"], float)
    assert "whyItMaps" in session


def test_no_fabricated_fallback(svc: CatalogService, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(svc, "_run_events_cli_json", MagicMock(return_value=[]))
    with pytest.raises(KeyError):
        svc.get_session_by_code("FAKE")
