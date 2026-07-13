"""Shared fixtures for Phase 0–2 contract tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from conferenceCatalogMCP.service import CatalogService
from conferenceCatalogMCP import server as server_module

FIXTURES = Path(__file__).parent / "fixtures"

REQUIRED_SESSION_FIELDS = [
    "asset",
    "sessionCode",
    "capability",
    "startDateTime",
    "endDateTime",
    "slideDeck",
    "recording",
    "transcript",
    "matchScore",
    "whyItMaps",
]


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def svc() -> CatalogService:
    return CatalogService()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """HTTP client with a fresh CatalogService instance."""
    service = CatalogService()
    monkeypatch.setattr(server_module, "catalog_service", service)
    return TestClient(server_module.app)


@pytest.fixture
def fixture_loader():
    return load_fixture


def expected_score(
    svc: CatalogService, signal: str, candidate: dict[str, Any]
) -> float:
    return svc._score_from_cli_candidate(signal, candidate)


def make_cli_router(
    search_payload: Any,
    details_by_code: dict[str, Any] | None = None,
):
    """Return a side_effect for _run_events_cli_json based on CLI args."""
    details_by_code = details_by_code or {}
    calls: list[list[str]] = []

    def _side_effect(args: list[str]) -> Any:
        calls.append(list(args))
        if args and args[0] == "sessions":
            return copy.deepcopy(search_payload)
        if args and args[0] == "session":
            code = args[1]
            if code in details_by_code:
                return copy.deepcopy(details_by_code[code])
            if isinstance(search_payload, list):
                for item in search_payload:
                    if isinstance(item, dict) and item.get("sessionCode") == code:
                        return copy.deepcopy(item)
            return []
        raise AssertionError(f"unexpected CLI args: {args}")

    mock = MagicMock(side_effect=_side_effect)
    mock.calls = calls  # type: ignore[attr-defined]
    return mock
