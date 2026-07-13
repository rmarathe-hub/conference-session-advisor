"""match_sessions contract tests."""

from __future__ import annotations

import copy
from unittest.mock import MagicMock

import pytest

from conferenceCatalogMCP.service import CatalogService
from tests.conftest import REQUIRED_SESSION_FIELDS, load_fixture, make_cli_router


@pytest.mark.parametrize(
    "signal",
    ["", "   ", "\n\t", None],
)
def test_rejects_empty_signal(svc: CatalogService, signal):
    with pytest.raises(ValueError, match="signal"):
        svc.match_sessions(signal)  # type: ignore[arg-type]


@pytest.mark.parametrize("limit", [0, -1, 11, 100, True, "3", 3.5])
def test_rejects_invalid_limit(svc: CatalogService, limit):
    with pytest.raises(ValueError, match="limit"):
        svc.match_sessions("agents", limit=limit)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "limit,expected_overfetch",
    [(1, 10), (2, 10), (3, 10), (4, 12), (10, 30)],
)
def test_overfetch_count(
    svc: CatalogService, monkeypatch: pytest.MonkeyPatch, limit: int, expected_overfetch: int
):
    mock = MagicMock(return_value=[])
    monkeypatch.setattr(svc, "_run_events_cli_json", mock)
    svc.match_sessions("agents", limit=limit, require_on_demand=False)
    args = mock.call_args.args[0]
    assert args[0] == "sessions"
    assert "--limit" in args
    assert args[args.index("--limit") + 1] == str(expected_overfetch)
    assert args[args.index("--event") + 1] == "build-2026"
    assert args[args.index("--query") + 1] == "agents"


def test_require_on_demand_filters(svc: CatalogService, monkeypatch: pytest.MonkeyPatch):
    search = load_fixture("search_mixed.json")
    monkeypatch.setattr(svc, "_run_events_cli_json", make_cli_router(search))
    out = svc.match_sessions("agents", limit=10, require_on_demand=True)
    codes = {r["sessionCode"] for r in out["results"]}
    assert "BRK102" not in codes
    for r in out["results"]:
        assert r["recording"] != "none"
    # Survivors exclude live-only BRK102 from the mixed fixture.
    assert out["total"] == 4


def test_require_on_demand_false_keeps_live_only(
    svc: CatalogService, monkeypatch: pytest.MonkeyPatch
):
    search = load_fixture("search_mixed.json")
    monkeypatch.setattr(svc, "_run_events_cli_json", make_cli_router(search))
    out = svc.match_sessions("workshop", limit=10, require_on_demand=False)
    codes = {r["sessionCode"] for r in out["results"]}
    assert "BRK102" in codes or out["total"] >= 1


def test_scheduled_only_filters_missing_both(
    svc: CatalogService, monkeypatch: pytest.MonkeyPatch
):
    search = [
        load_fixture("session_with_recording.json"),
        load_fixture("session_start_only.json"),
        load_fixture("session_end_only.json"),
        load_fixture("session_no_times.json"),
    ]
    monkeypatch.setattr(svc, "_run_events_cli_json", make_cli_router(search))
    out = svc.match_sessions("schedule", limit=10, scheduled_only=True, require_on_demand=True)
    codes = {r["sessionCode"] for r in out["results"]}
    assert "BRK105" not in codes
    assert "BRK101" in codes or "BRK103" in codes or "BRK104" in codes


def test_empty_search_returns_empty_results(
    svc: CatalogService, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(svc, "_run_events_cli_json", MagicMock(return_value=[]))
    out = svc.match_sessions("irrelevant xyzzy", limit=3)
    assert out["signal"] == "irrelevant xyzzy"
    assert out["results"] == []
    assert out["total"] == 0
    assert "catalogVersion" in out


def test_result_envelope_and_ordering(
    svc: CatalogService, monkeypatch: pytest.MonkeyPatch
):
    search = load_fixture("search_mixed.json")
    monkeypatch.setattr(svc, "_run_events_cli_json", make_cli_router(search))
    out = svc.match_sessions("agent observability", limit=3, require_on_demand=True)
    assert set(out) == {"signal", "results", "total", "catalogVersion"}
    assert out["signal"] == "agent observability"
    assert len(out["results"]) <= 3
    assert out["total"] >= len(out["results"])
    scores = [r["matchScore"] for r in out["results"]]
    assert scores == sorted(scores, reverse=True)
    for r in out["results"]:
        for field in REQUIRED_SESSION_FIELDS:
            assert field in r


def test_shortlist_hydration_only_for_limit(
    svc: CatalogService, monkeypatch: pytest.MonkeyPatch
):
    search = []
    for i in range(12):
        search.append(
            {
                "sessionCode": f"S{i:03d}",
                "title": f"agent observability topic {i}",
                "description": "agent observability content",
                "onDemand": f"https://medius.microsoft.com/Embed/video-nc/aaaaaaaa-bbbb-cccc-dddd-{i:012d}",
                "hasOnDemand": True,
            }
        )
    calls: list[list[str]] = []

    def router(args):
        calls.append(list(args))
        if args[0] == "sessions":
            return copy.deepcopy(search)
        code = args[1]
        return next(c for c in search if c["sessionCode"] == code)

    monkeypatch.setattr(svc, "_run_events_cli_json", router)
    out = svc.match_sessions("agent observability", limit=3)
    assert len(out["results"]) == 3
    assert out["total"] == 12
    session_calls = [c for c in calls if c[0] == "session"]
    assert len(session_calls) == 3
    hydrated_codes = {c[1] for c in session_calls}
    result_codes = {r["sessionCode"] for r in out["results"]}
    assert hydrated_codes == result_codes


def test_no_invented_sessions(svc: CatalogService, monkeypatch: pytest.MonkeyPatch):
    search = load_fixture("search_mixed.json")
    known = {c["sessionCode"] for c in search}
    monkeypatch.setattr(svc, "_run_events_cli_json", make_cli_router(search))
    out = svc.match_sessions("agents", limit=5, require_on_demand=False)
    for r in out["results"]:
        assert r["sessionCode"] in known


def test_hydration_empty_detail_keeps_search_candidate(
    svc: CatalogService, monkeypatch: pytest.MonkeyPatch
):
    search = [
        {
            "sessionCode": "KEEP1",
            "title": "agent observability",
            "description": "agent observability",
            "onDemand": "https://medius.microsoft.com/Embed/video-nc/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "hasOnDemand": True,
        }
    ]

    def router(args):
        if args[0] == "sessions":
            return search
        return []

    monkeypatch.setattr(svc, "_run_events_cli_json", router)
    out = svc.match_sessions("agent observability", limit=1)
    assert out["results"][0]["sessionCode"] == "KEEP1"


def test_duplicate_codes_stable(svc: CatalogService, monkeypatch: pytest.MonkeyPatch):
    dup = {
        "sessionCode": "DUP1",
        "title": "agent observability",
        "description": "agent observability",
        "onDemand": "https://medius.microsoft.com/Embed/video-nc/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "hasOnDemand": True,
    }
    search = [copy.deepcopy(dup), copy.deepcopy(dup)]
    monkeypatch.setattr(svc, "_run_events_cli_json", make_cli_router(search))
    out1 = svc.match_sessions("agent observability", limit=2)
    out2 = svc.match_sessions("agent observability", limit=2)
    assert [r["sessionCode"] for r in out1["results"]] == [
        r["sessionCode"] for r in out2["results"]
    ]


def test_preserves_signal_whitespace_trim(
    svc: CatalogService, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(svc, "_run_events_cli_json", MagicMock(return_value=[]))
    out = svc.match_sessions("  agents  ", limit=1)
    assert out["signal"] == "agents"
