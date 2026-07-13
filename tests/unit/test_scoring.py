"""Exact scoring-formula unit tests."""

from __future__ import annotations

import pytest

from conferenceCatalogMCP.service import CatalogService


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Agent Observability", {"agent", "observability"}),
        ("ai-agents!!!", {"ai", "agents"}),
        ("  Foo   Bar  ", {"foo", "bar"}),
        ("", set()),
        ("@@@", set()),
        ("v2 roadmap 101", {"v2", "roadmap", "101"}),
        ("café agents", {"caf", "agents"}),  # non-ascii letters dropped by [a-z0-9]+
        ("Agent Agent Agents", {"agent", "agents"}),
    ],
)
def test_tokenize(svc: CatalogService, text: str, expected: set[str]):
    assert svc.tokenize(text) == expected


def _manual_score(svc: CatalogService, signal: str, candidate: dict) -> float:
    """Recompute score independently for exact assertions."""
    signal_tokens = svc.tokenize(signal)
    title = str(candidate.get("title") or "")
    description = str(candidate.get("description") or "")
    title_tokens = svc.tokenize(title)
    body = title_tokens | svc.tokenize(description)
    overlap = (len(signal_tokens & body) / len(signal_tokens)) if signal_tokens else 0.0
    norm = " ".join(svc.tokenize(signal))  # join of unique set is unordered — use ordered tokens
    # Match implementation: ordered findall join
    import re

    token_re = re.compile(r"[a-z0-9]+")
    normalized_signal = " ".join(token_re.findall((signal or "").lower()))
    title_norm = " ".join(token_re.findall(title.lower()))
    desc_norm = " ".join(token_re.findall(description.lower()))
    exact = (
        1.0
        if normalized_signal
        and (normalized_signal in title_norm or normalized_signal in desc_norm)
        else 0.0
    )
    title_overlap = 1.0 if signal_tokens and (signal_tokens & title_tokens) else 0.0
    transcript = 1.0 if svc._resolve_transcript(candidate) != "none" else 0.0
    return min(1.0, 0.60 * overlap + 0.20 * exact + 0.15 * title_overlap + 0.05 * transcript)


@pytest.mark.parametrize(
    "signal,candidate",
    [
        (
            "agent observability",
            {
                "title": "Agent observability deep dive",
                "description": "other",
                "captionFileLink": "https://x/t.vtt",
            },
        ),
        (
            "secure enterprise agents",
            {
                "title": "Unrelated",
                "description": "secure enterprise agents workshop",
            },
        ),
        (
            "zzz missing",
            {"title": "Hello", "description": "World"},
        ),
        (
            "",
            {"title": "Agent", "description": "observability"},
        ),
        (
            "agent agent observability",
            {
                "title": "Agent observability",
                "description": "agent observability guide",
                "transcript": "https://x/t.txt",
            },
        ),
        (
            "AI Agents 101",
            {"title": "ai agents 101", "description": ""},
        ),
        (
            "x" * 500 + " agents",
            {"title": "agents", "description": ""},
        ),
    ],
)
def test_score_matches_formula(svc: CatalogService, signal: str, candidate: dict):
    got = svc._score_from_cli_candidate(signal, candidate)
    expected = _manual_score(svc, signal, candidate)
    assert got == pytest.approx(expected)
    assert 0.0 <= got <= 1.0


def test_score_cap_at_one(svc: CatalogService):
    candidate = {
        "title": "agent observability",
        "description": "agent observability agent observability",
        "captionFileLink": "https://x/t.vtt",
    }
    score = svc._score_from_cli_candidate("agent observability", candidate)
    assert score == 1.0


def test_score_deterministic(svc: CatalogService):
    candidate = {
        "title": "Agent observability",
        "description": "for ai agents",
        "onDemand": "https://medius.microsoft.com/Embed/video-nc/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    }
    scores = [
        svc._score_from_cli_candidate("agent observability", candidate) for _ in range(20)
    ]
    assert len(set(scores)) == 1


def test_title_only_vs_description_only(svc: CatalogService):
    title_only = svc._score_from_cli_candidate(
        "observability", {"title": "observability rocks", "description": "other"}
    )
    desc_only = svc._score_from_cli_candidate(
        "observability", {"title": "other", "description": "observability rocks"}
    )
    assert title_only > desc_only  # title_token_overlap bonus


def test_transcript_bonus(svc: CatalogService):
    base = {"title": "zzz", "description": "zzz"}
    with_t = {**base, "transcript": "https://example.com/t.txt"}
    assert svc._score_from_cli_candidate("nope", with_t) == pytest.approx(0.05)
    assert svc._score_from_cli_candidate("nope", base) == pytest.approx(0.0)


def test_exact_phrase_in_title_and_description(svc: CatalogService):
    signal = "ai agents"
    in_title = svc._score_from_cli_candidate(
        signal, {"title": "ai agents workshop", "description": ""}
    )
    in_desc = svc._score_from_cli_candidate(
        signal, {"title": "workshop", "description": "ai agents today"}
    )
    assert in_title >= 0.20
    assert in_desc >= 0.20
