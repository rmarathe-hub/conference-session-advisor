"""CatalogService — authoritative Build catalog access via @microsoft/events-cli."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any

EVENT_SLUG = "build-2026"
DEFAULT_CLI_TIMEOUT_SECONDS = 90

_GUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_TOKEN_RE = re.compile(r"[a-z0-9]+")


class EventsCliError(RuntimeError):
    """Raised when the events CLI cannot be run or returns a failure."""


class CatalogService:
    """Grounded session matching against Microsoft Build via events-cli."""

    def catalog_version(self) -> str:
        """Server catalog date stamp for response envelopes."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _run_events_cli_json(self, args: list[str]) -> Any:
        """Run `npx -y @microsoft/events-cli <args>` and parse JSON stdout.

        Every catalog read must use this function. No alternate catalog sources.
        """
        npx = shutil.which("npx")
        if not npx:
            raise EventsCliError(
                "npx was not found on PATH. Install Node.js 22+ and ensure "
                "npx is available before querying the Build catalog."
            )

        timeout = int(
            os.environ.get("EVENTS_CLI_TIMEOUT_SECONDS", DEFAULT_CLI_TIMEOUT_SECONDS)
        )
        cmd = [npx, "-y", "@microsoft/events-cli", *args]
        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise EventsCliError(
                f"events-cli timed out after {timeout} seconds. "
                "Raise EVENTS_CLI_TIMEOUT_SECONDS if needed."
            ) from exc

        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip() or "(no stderr)"
            raise EventsCliError(
                f"events-cli exited with code {completed.returncode}: {stderr}"
            )

        stdout = (completed.stdout or "").strip()
        if not stdout:
            raise EventsCliError("events-cli returned empty stdout; expected JSON.")

        try:
            return json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise EventsCliError(
                f"events-cli stdout was not valid JSON: {exc}"
            ) from exc

    def _field(self, candidate: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in candidate and candidate[key] is not None:
                return candidate[key]
        return None

    def _as_none_string(self, value: Any) -> str:
        if value is None:
            return "none"
        if isinstance(value, str):
            text = value.strip()
            if not text or text.lower() in {"none", "null", "n/a"}:
                return "none"
            return text
        text = str(value).strip()
        return text if text else "none"

    def _resolve_transcript(self, candidate: dict[str, Any]) -> str:
        """Resolve transcript URL per contract order."""
        caption = self._field(candidate, "captionFileLink")
        if caption:
            resolved = self._as_none_string(caption)
            if resolved != "none":
                return resolved

        transcript = self._field(candidate, "transcript")
        if transcript:
            resolved = self._as_none_string(transcript)
            if resolved != "none":
                return resolved

        for key in ("sessionId", "onDemand", "slideDeck", "downloadVideoLink"):
            raw = self._field(candidate, key)
            if raw is None:
                continue
            match = _GUID_RE.search(str(raw))
            if match:
                return f"https://medius.microsoft.com/video/asset/Transcript/{match.group(0)}"

        return "none"

    def _strength_band(self, score: float) -> str:
        if score >= 0.75:
            return "High"
        if score >= 0.50:
            return "Medium"
        return "Low"

    def _why_it_maps(self, signal: str, candidate: dict[str, Any], score: float) -> str:
        """Short human-readable rationale with strength band."""
        band = self._strength_band(score)
        title = self._as_none_string(self._field(candidate, "title", "asset"))
        code = self._as_none_string(self._field(candidate, "sessionCode", "code"))
        signal_text = (signal or "").strip() or "the signal"
        if title != "none":
            return (
                f"{band} match: session {code} ({title}) aligns with {signal_text}."
            )
        return f"{band} match: session {code} aligns with {signal_text}."

    def _normalize_session(
        self,
        candidate: dict[str, Any],
        *,
        signal: str | None = None,
        match_score: float | None = None,
    ) -> dict[str, Any]:
        """Map a CLI candidate into the stable normalized session shape."""
        if not isinstance(candidate, dict):
            raise TypeError("candidate must be a dict")

        score = 0.0 if match_score is None else float(match_score)
        score = max(0.0, min(1.0, score))

        recording = self._as_none_string(
            self._field(candidate, "onDemand", "recording", "downloadVideoLink")
        )
        slide_deck = self._as_none_string(self._field(candidate, "slideDeck"))
        transcript = self._resolve_transcript(candidate)

        why = "none"
        if signal is not None:
            why = self._why_it_maps(signal, candidate, score)

        return {
            "asset": self._as_none_string(self._field(candidate, "title", "asset")),
            "sessionCode": self._as_none_string(
                self._field(candidate, "sessionCode", "code")
            ),
            "capability": self._as_none_string(
                self._field(candidate, "description", "capability")
            ),
            "startDateTime": self._as_none_string(
                self._field(candidate, "startDateTime", "start")
            ),
            "endDateTime": self._as_none_string(
                self._field(candidate, "endDateTime", "end")
            ),
            "slideDeck": slide_deck,
            "recording": recording,
            "transcript": transcript,
            "matchScore": score,
            "whyItMaps": why,
        }

    def tokenize(self, text: str) -> set[str]:
        """Lowercase alphanumeric tokens (shared by scoring)."""
        return set(_TOKEN_RE.findall((text or "").lower()))

    def _score_from_cli_candidate(self, signal: str, candidate: dict[str, Any]) -> float:
        """Deterministic score in [0.0, 1.0] from the required weighted formula."""
        signal_tokens = self.tokenize(signal)
        title = str(self._field(candidate, "title", "asset") or "")
        description = str(self._field(candidate, "description", "capability") or "")
        title_tokens = self.tokenize(title)
        body_tokens = title_tokens | self.tokenize(description)

        if signal_tokens:
            overlap = len(signal_tokens & body_tokens) / len(signal_tokens)
        else:
            overlap = 0.0

        normalized_signal = " ".join(_TOKEN_RE.findall((signal or "").lower()))
        if normalized_signal:
            title_norm = " ".join(_TOKEN_RE.findall(title.lower()))
            desc_norm = " ".join(_TOKEN_RE.findall(description.lower()))
            exact_phrase = (
                1.0
                if normalized_signal in title_norm or normalized_signal in desc_norm
                else 0.0
            )
        else:
            exact_phrase = 0.0

        title_token_overlap = (
            1.0 if signal_tokens and (signal_tokens & title_tokens) else 0.0
        )

        transcript_exists = (
            1.0 if self._resolve_transcript(candidate) != "none" else 0.0
        )

        score = min(
            1.0,
            0.60 * overlap
            + 0.20 * exact_phrase
            + 0.15 * title_token_overlap
            + 0.05 * transcript_exists,
        )
        return float(score)

    def _has_on_demand(self, candidate: dict[str, Any]) -> bool:
        flag = self._field(candidate, "hasOnDemand")
        if flag is True:
            return True
        if flag is False:
            recording = self._as_none_string(
                self._field(candidate, "onDemand", "recording", "downloadVideoLink")
            )
            return recording != "none"
        recording = self._as_none_string(
            self._field(candidate, "onDemand", "recording", "downloadVideoLink")
        )
        return recording != "none"

    def _has_schedule(self, candidate: dict[str, Any]) -> bool:
        start = self._as_none_string(self._field(candidate, "startDateTime", "start"))
        end = self._as_none_string(self._field(candidate, "endDateTime", "end"))
        # scheduled_only removes candidates missing BOTH start and end.
        return not (start == "none" and end == "none")

    def _coerce_session_list(self, payload: Any) -> list[dict[str, Any]]:
        if payload is None:
            return []
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("sessions", "results", "data", "items"):
                nested = payload.get(key)
                if isinstance(nested, list):
                    return [item for item in nested if isinstance(item, dict)]
            if self._field(payload, "sessionCode", "code"):
                return [payload]
        return []

    def _merge_candidate(
        self, base: dict[str, Any], detail: dict[str, Any]
    ) -> dict[str, Any]:
        merged = dict(base)
        for key, value in detail.items():
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            merged[key] = value
        return merged

    def match_sessions(
        self,
        signal: str,
        limit: int = 3,
        scheduled_only: bool = False,
        require_on_demand: bool = True,
    ) -> dict[str, Any]:
        """Match a signal to grounded Build sessions."""
        if signal is None or not str(signal).strip():
            raise ValueError("signal must be a non-empty string")
        signal = str(signal).strip()

        if not isinstance(limit, int) or isinstance(limit, bool) or not (1 <= limit <= 10):
            raise ValueError("limit must be an integer satisfying 1 <= limit <= 10")

        over_fetch = max(limit * 3, 10)
        raw = self._run_events_cli_json(
            [
                "sessions",
                "--event",
                EVENT_SLUG,
                "--query",
                signal,
                "--limit",
                str(over_fetch),
                "--json",
            ]
        )
        candidates = self._coerce_session_list(raw)

        survivors: list[dict[str, Any]] = []
        for candidate in candidates:
            if require_on_demand and not self._has_on_demand(candidate):
                continue
            if scheduled_only and not self._has_schedule(candidate):
                continue
            score = self._score_from_cli_candidate(signal, candidate)
            normalized = self._normalize_session(
                candidate, signal=signal, match_score=score
            )
            survivors.append({"candidate": candidate, "session": normalized, "score": score})

        survivors.sort(key=lambda item: item["score"], reverse=True)
        total = len(survivors)
        shortlist = survivors[:limit]

        results: list[dict[str, Any]] = []
        for item in shortlist:
            code = item["session"].get("sessionCode", "none")
            if code == "none":
                results.append(item["session"])
                continue
            detail_raw = self._run_events_cli_json(
                ["session", code, "--event", EVENT_SLUG, "--json"]
            )
            detail_list = self._coerce_session_list(detail_raw)
            if not detail_list:
                results.append(item["session"])
                continue
            merged = self._merge_candidate(item["candidate"], detail_list[0])
            rescore = self._score_from_cli_candidate(signal, merged)
            results.append(
                self._normalize_session(merged, signal=signal, match_score=rescore)
            )

        results.sort(key=lambda session: session["matchScore"], reverse=True)

        return {
            "signal": signal,
            "results": results,
            "total": total,
            "catalogVersion": self.catalog_version(),
        }

    def get_session_by_code(self, session_code: str) -> dict[str, Any]:
        """Return one normalized session by authoritative code."""
        if session_code is None or not str(session_code).strip():
            raise ValueError("session_code must be a non-empty string")
        session_code = str(session_code).strip()

        raw = self._run_events_cli_json(
            ["session", session_code, "--event", EVENT_SLUG, "--json"]
        )
        sessions = self._coerce_session_list(raw)
        if not sessions:
            raise KeyError(session_code)

        candidate = sessions[0]
        found_code = self._as_none_string(
            self._field(candidate, "sessionCode", "code")
        )
        if found_code == "none":
            raise KeyError(session_code)

        score = self._score_from_cli_candidate(session_code, candidate)
        return {
            "session": self._normalize_session(
                candidate, signal=session_code, match_score=score
            )
        }
