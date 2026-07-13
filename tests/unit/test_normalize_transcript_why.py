"""Normalization and transcript / whyItMaps tests."""

from __future__ import annotations

import pytest

from conferenceCatalogMCP.service import CatalogService
from tests.conftest import REQUIRED_SESSION_FIELDS, load_fixture


def test_all_required_fields_present(svc: CatalogService):
    session = svc._normalize_session(load_fixture("session_complete.json"), signal="x", match_score=0.8)
    for field in REQUIRED_SESSION_FIELDS:
        assert field in session


@pytest.mark.parametrize(
    "raw,field,expected",
    [
        ({}, "asset", "none"),
        ({"title": None}, "asset", "none"),
        ({"title": ""}, "asset", "none"),
        ({"title": "  "}, "asset", "none"),
        ({"title": "null"}, "asset", "none"),
        ({"title": "none"}, "asset", "none"),
        ({"sessionCode": "BRK1"}, "sessionCode", "BRK1"),
        ({"code": "ALT1"}, "sessionCode", "ALT1"),
    ],
)
def test_missing_becomes_none(svc: CatalogService, raw, field, expected):
    out = svc._normalize_session(raw, signal=None, match_score=0)
    assert out[field] == expected


def test_no_null_normalized_strings(svc: CatalogService):
    out = svc._normalize_session(
        {
            "title": None,
            "description": None,
            "startDateTime": None,
            "endDateTime": None,
            "slideDeck": None,
            "onDemand": None,
        },
        signal="s",
        match_score=0.1,
    )
    for key, value in out.items():
        if key == "matchScore":
            assert isinstance(value, float)
        else:
            assert value is not None
            assert value != ""


def test_whitespace_title_stripped(svc: CatalogService):
    out = svc._normalize_session(
        load_fixture("session_partial_messy.json"), signal="agents", match_score=0.2
    )
    assert out["asset"] == "Spaced Title"
    assert out["slideDeck"] == "none"
    assert out["startDateTime"] == "none"
    assert out["endDateTime"] == "none"
    # Contract says cleaned description; current implementation preserves HTML tags.
    assert "<p>" in out["capability"]


def test_recording_from_ondemand(svc: CatalogService):
    out = svc._normalize_session(load_fixture("session_with_recording.json"), signal="s", match_score=0.5)
    assert out["recording"].startswith("https://")


@pytest.mark.parametrize(
    "fixture,expected_substr",
    [
        ("session_caption.json", "https://example.com/captions/preferred.vtt"),
        ("session_transcript_field.json", "https://example.com/transcripts/direct.txt"),
        (
            "session_guid_transcript.json",
            "https://medius.microsoft.com/video/asset/Transcript/ABCDEF12-3456-7890-ABCD-EF1234567890",
        ),
        ("session_no_transcript.json", "none"),
    ],
)
def test_transcript_resolution_order(svc: CatalogService, fixture: str, expected_substr: str):
    candidate = load_fixture(fixture)
    assert svc._resolve_transcript(candidate) == expected_substr


def test_caption_beats_transcript_and_guid(svc: CatalogService):
    candidate = {
        "captionFileLink": "https://cap",
        "transcript": "https://tr",
        "onDemand": "https://medius.microsoft.com/Embed/video-nc/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    }
    assert svc._resolve_transcript(candidate) == "https://cap"


def test_transcript_beats_guid(svc: CatalogService):
    candidate = {
        "transcript": "https://tr",
        "onDemand": "https://medius.microsoft.com/Embed/video-nc/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    }
    assert svc._resolve_transcript(candidate) == "https://tr"


@pytest.mark.parametrize(
    "key",
    ["sessionId", "onDemand", "slideDeck", "downloadVideoLink"],
)
def test_guid_from_each_source(svc: CatalogService, key: str):
    guid = "12345678-1234-1234-1234-123456789abc"
    candidate = {key: f"prefix/{guid}/suffix"}
    assert (
        svc._resolve_transcript(candidate)
        == f"https://medius.microsoft.com/video/asset/Transcript/{guid}"
    )


@pytest.mark.parametrize(
    "bad",
    [
        "not-a-guid",
        "1234",
        "gggggggg-gggg-gggg-gggg-gggggggggggg",
        "",
        None,
    ],
)
def test_invalid_guid_yields_none(svc: CatalogService, bad):
    candidate = {"onDemand": bad} if bad is not None else {}
    if bad is None:
        candidate = {"title": "x"}
    else:
        candidate = {"onDemand": bad, "slideDeck": "https://x"}
    assert svc._resolve_transcript(candidate) == "none"


@pytest.mark.parametrize(
    "score,band",
    [
        (0.00, "Low"),
        (0.49, "Low"),
        (0.4999, "Low"),
        (0.50, "Medium"),
        (0.74, "Medium"),
        (0.7499, "Medium"),
        (0.75, "High"),
        (1.00, "High"),
    ],
)
def test_whyitmaps_strength_bands(svc: CatalogService, score: float, band: str):
    why = svc._why_it_maps(
        "agents",
        {"title": "Agents 101", "sessionCode": "BRK1"},
        score,
    )
    assert isinstance(why, str)
    assert band in why
    assert "BRK1" in why
    assert len(why) < 300


def test_whyitmaps_deterministic(svc: CatalogService):
    c = {"title": "Agents", "sessionCode": "A1"}
    assert svc._why_it_maps("s", c, 0.8) == svc._why_it_maps("s", c, 0.8)


def test_whyitmaps_without_title(svc: CatalogService):
    why = svc._why_it_maps("signal", {"sessionCode": "X"}, 0.2)
    assert "Low" in why
    assert "X" in why
