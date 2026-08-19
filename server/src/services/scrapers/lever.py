"""Lever board scraper. Public JSON API — no token."""

import html
import re
from datetime import datetime, timezone
from typing import Any

import httpx

_BASE = "https://api.lever.co/v0/postings/{board}?mode=json"
_TIMEOUT = 30


def _strip_html(raw: str) -> str:
    text = html.unescape(raw or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_board(board: str) -> list[dict[str, Any]]:
    resp = httpx.get(_BASE.format(board=board), timeout=_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):  # bad slug -> {"ok": false, ...}
        return []

    out: list[dict[str, Any]] = []
    for job in data:
        cats = job.get("categories") or {}
        parts = []
        if job.get("descriptionPlain"):
            parts.append(job["descriptionPlain"])
        elif job.get("description"):
            parts.append(_strip_html(job["description"]))
        for lst in job.get("lists") or []:
            head = f"{lst['text']}:\n" if lst.get("text") else ""
            parts.append(head + _strip_html(lst.get("content", "")))
        if job.get("additionalPlain"):
            parts.append(job["additionalPlain"])
        description = "\n\n".join(p for p in parts if p).strip()

        created = job.get("createdAt")
        posted_at = None
        if created:
            try:
                posted_at = datetime.fromtimestamp(created / 1000, tz=timezone.utc).isoformat()
            except (ValueError, OSError):
                posted_at = None

        out.append(
            {
                "external_id": str(job.get("id", "")),
                "title": job.get("text", "No Title"),
                "location": cats.get("location")
                or ("Remote" if job.get("workplaceType") == "remote" else None),
                "url": job.get("hostedUrl") or job.get("applyUrl") or "",
                "description": description,
                "posted_at": posted_at,
            }
        )
    return out
