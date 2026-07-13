"""CatalogService — authoritative Build catalog access via @microsoft/events-cli."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
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
