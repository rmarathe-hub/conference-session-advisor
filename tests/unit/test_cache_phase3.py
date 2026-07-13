"""Unit tests for in-process and Blob TTL caches (Phase 3.1 / 3.2)."""

from __future__ import annotations

import json
import logging
import time
from unittest.mock import MagicMock, patch

import pytest

from conferenceCatalogMCP.blob_cache import BlobStorageCache, sanitize_blob_key
from conferenceCatalogMCP.service import CatalogService, InProcessTTLCache


def test_inprocess_set_get_and_ttl_expiry():
    cache = InProcessTTLCache()
    cache.set("k", {"ok": True})
    assert cache.get("k", ttl=60) == {"ok": True}
    cache._store["k"]["_created_at"] = time.time() - 120
    assert cache.get("k", ttl=60) is None
    assert "k" not in cache._store


def test_inprocess_miss():
    assert InProcessTTLCache().get("missing", ttl=10) is None


def test_match_sessions_second_call_cache_hit(caplog, monkeypatch):
    svc = CatalogService()
    search = [
        {
            "sessionCode": "C1",
            "title": "agent observability",
            "description": "agent observability",
            "onDemand": "https://medius.microsoft.com/Embed/video-nc/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "hasOnDemand": True,
        }
    ]
    calls: list[list[str]] = []

    def router(args):
        calls.append(list(args))
        if args[0] == "sessions":
            return search
        return search[0]

    monkeypatch.setattr(svc, "_run_events_cli_json", router)
    with caplog.at_level(logging.INFO):
        first = svc.match_sessions("agent observability", limit=1)
        second = svc.match_sessions("agent observability", limit=1)
    assert first == second
    assert any("Cache HIT" in r.message for r in caplog.records)
    # CLI only on first call (sessions + session hydrate)
    assert len(calls) >= 1
    assert all(c[0] in {"sessions", "session"} for c in calls)
    # Second call must not add CLI invocations
    call_count_after_first = len(calls)
    svc.match_sessions("agent observability", limit=1)
    assert len(calls) == call_count_after_first


def test_blob_disabled_without_credentials(monkeypatch):
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_ACCOUNT_NAME", raising=False)
    cache = BlobStorageCache()
    assert cache.enabled is False
    assert cache.get("k", 60) is None
    cache.set("k", {"a": 1})  # no-op


def test_blob_get_set_with_mocked_container(monkeypatch):
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")

    uploaded: dict[str, bytes] = {}

    class FakeBlob:
        def __init__(self, name: str):
            self.name = name

        def exists(self):
            return self.name in uploaded

        def download_blob(self):
            data = uploaded[self.name]

            class Reader:
                def readall(self_inner):
                    return data

            return Reader()

        def delete_blob(self):
            uploaded.pop(self.name, None)

        def upload_blob(self, data, overwrite=True):
            uploaded[self.name] = data

    class FakeContainer:
        def get_blob_client(self, name):
            return FakeBlob(name)

        def create_container(self):
            return None

    class FakeService:
        def get_container_client(self, name):
            return FakeContainer()

    with patch(
        "azure.storage.blob.BlobServiceClient.from_connection_string",
        return_value=FakeService(),
    ):
        cache = BlobStorageCache(container_name="mcp-cache")
        assert cache.enabled is True
        cache.set("hello world", {"x": 1})
        assert sanitize_blob_key("hello world") in uploaded
        got = cache.get("hello world", ttl=300)
        assert got == {"x": 1}

        entry = json.loads(uploaded[sanitize_blob_key("hello world")])
        entry["_created_at"] = time.time() - 999
        uploaded[sanitize_blob_key("hello world")] = json.dumps(entry).encode()
        assert cache.get("hello world", ttl=10) is None


def test_blob_get_failure_is_swallowed(monkeypatch):
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT_NAME", "acct")

    class BoomContainer:
        def create_container(self):
            return None

        def get_blob_client(self, name):
            raise RuntimeError("boom")

    class FakeService:
        def get_container_client(self, name):
            return BoomContainer()

    with patch("azure.identity.DefaultAzureCredential", return_value=MagicMock()), patch(
        "azure.storage.blob.BlobServiceClient", return_value=FakeService()
    ):
        cache = BlobStorageCache()
        assert cache.get("k", 30) is None
        cache.set("k", {"a": 1})  # must not raise


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("hello world", "hello_world"),
        ("a(b)c", "a{b}c"),
        ("a:b", "a-b"),
        ("mix (x): y", "mix_{x}-_y"),
    ],
)
def test_sanitize_helpers_used_by_blob(raw, expected):
    assert sanitize_blob_key(raw) == expected


def test_sanitize_max_length_1024():
    long_key = "a" * 2000
    assert len(sanitize_blob_key(long_key)) == 1024


def test_dual_tier_read_blob_then_populate_memory(monkeypatch, caplog):
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_ACCOUNT_NAME", raising=False)
    payload = {
        "signal": "agents",
        "results": [],
        "total": 0,
        "catalogVersion": "2026-01-01",
    }

    class FakeBlobCache:
        enabled = True

        def get(self, key, ttl):
            return payload

        def set(self, key, value):
            raise AssertionError("set should not be required for this read test")

    svc = CatalogService()
    assert svc._blob is None
    svc._blob = FakeBlobCache()  # type: ignore[assignment]
    svc._memory.clear()
    calls: list[list[str]] = []

    def boom(args):
        calls.append(list(args))
        raise AssertionError("CLI should not run on blob cache hit")

    monkeypatch.setattr(svc, "_run_events_cli_json", boom)
    with caplog.at_level(logging.INFO):
        out = svc.match_sessions("agents", limit=1)
    assert out == payload
    assert calls == []
    assert any("Cache HIT" in r.message for r in caplog.records)
    assert svc._memory.get(svc._match_cache_key("agents", 1, False, True), 300) == payload


def test_dual_tier_write_calls_blob(monkeypatch):
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_ACCOUNT_NAME", raising=False)
    svc = CatalogService()
    written: list[tuple[str, object]] = []

    class FakeBlobCache:
        enabled = True

        def get(self, key, ttl):
            return None

        def set(self, key, value):
            written.append((key, value))

    svc._blob = FakeBlobCache()  # type: ignore[assignment]
    search = [
        {
            "sessionCode": "C1",
            "title": "agent observability",
            "description": "agent observability",
            "onDemand": "https://medius.microsoft.com/Embed/video-nc/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "hasOnDemand": True,
        }
    ]

    def router(args):
        if args[0] == "sessions":
            return search
        return search[0]

    monkeypatch.setattr(svc, "_run_events_cli_json", router)
    out = svc.match_sessions("agent observability", limit=1)
    assert written
    assert written[0][1] == out
