"""Update check against this repo's GitHub releases. Nothing else is sent.

Telemetry is off. The request is a single GET with a fixed User-Agent and no client id.
Set PLOTWEAVER_NO_UPDATE_CHECK=1 to skip it (tests do).
"""

from __future__ import annotations

import os

import httpx

from plotweaver.appinfo import APP_VERSION, GITHUB_REPO


def check_for_update() -> str | None:
    """Return a newer tag, or None when this build is current, offline, or checks are disabled."""
    if os.environ.get("PLOTWEAVER_NO_UPDATE_CHECK"):
        return None
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    try:
        response = httpx.get(
            url,
            headers={"User-Agent": "plotweaver", "Accept": "application/vnd.github+json"},
            timeout=5.0,
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError:
        return None
    if not isinstance(payload, dict):
        return None
    tag = str(payload.get("tag_name") or "")
    if tag in {"", f"v{APP_VERSION}", APP_VERSION}:
        return None
    return tag
