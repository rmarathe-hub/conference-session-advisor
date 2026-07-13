"""Optional real-CLI integration tests (skipped by default via pytest.ini)."""

from __future__ import annotations

import pytest

from conferenceCatalogMCP.service import CatalogService, EventsCliError

pytestmark = pytest.mark.real_cli


@pytest.fixture(scope="module")
def live_svc() -> CatalogService:
    return CatalogService()


def test_events_cli_sessions_json(live_svc: CatalogService):
    try:
        data = live_svc._run_events_cli_json(
            [
                "sessions",
                "--event",
                "build-2026",
                "--query",
                "ai agents",
                "--limit",
                "3",
                "--json",
            ]
        )
    except EventsCliError as exc:
        pytest.skip(f"live events-cli unavailable: {exc}")
    assert isinstance(data, list)


def test_match_sessions_live_grounding(live_svc: CatalogService):
    try:
        out = live_svc.match_sessions(
            "agent observability", limit=2, require_on_demand=True
        )
    except EventsCliError as exc:
        pytest.skip(f"live events-cli unavailable: {exc}")
    assert len(out["results"]) <= 2
    for row in out["results"]:
        try:
            detail = live_svc._run_events_cli_json(
                ["session", row["sessionCode"], "--event", "build-2026", "--json"]
            )
        except EventsCliError as exc:
            pytest.skip(f"live session lookup unavailable: {exc}")
        if isinstance(detail, list):
            assert detail
            assert detail[0].get("sessionCode") == row["sessionCode"]
        else:
            assert detail.get("sessionCode") == row["sessionCode"]
