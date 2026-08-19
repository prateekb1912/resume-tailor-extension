"""Greenhouse board scraper. Public JSON API — no token, no auth.

Each source module exposes fetch_board(board) -> list[dict] with a normalized shape:
{external_id, title, location, url, description, posted_at (ISO str | None)}.
Lever/Workable/LinkedIn will mirror this so scraper_service treats them uniformly.
"""

import html
import re
from typing import Any

import httpx

_BASE = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
_TIMEOUT = 30


def _strip_html(raw: str) -> str:
    text = html.unescape(raw or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_board(board: str) -> list[dict[str, Any]]:
    resp = httpx.get(_BASE.format(board=board), timeout=_TIMEOUT)
    resp.raise_for_status()
    jobs = resp.json().get("jobs", [])

    out: list[dict[str, Any]] = []
    for job in jobs:
        out.append(
            {
                "external_id": str(job.get("id", "")),
                "title": job.get("title", ""),
                "location": (job.get("location") or {}).get("name"),
                "url": job.get("absolute_url", ""),
                "description": _strip_html(job.get("content", "")),
                "posted_at": job.get("updated_at") or job.get("first_published"),
            }
        )
    return out
