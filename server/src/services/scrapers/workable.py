"""Workable scraper. Public JSON feed — no token, no company list.

Workable's global feed (jobs.workable.com/api/v1/jobs) returns full job records —
company, url, location, description — for a location query. That's the "better way
to search" than a hand-maintained company list: any company hiring on Workable shows up
automatically. We page the feed and normalize straight into the shared job shape.
"""

import html
import re
from typing import Any

import httpx

_FEED = "https://jobs.workable.com/api/v1/jobs"
_TIMEOUT = 30


def _strip_html(raw: str) -> str:
    text = html.unescape(raw or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize(job: dict[str, Any]) -> dict[str, Any]:
    company = (job.get("company") or {}).get("title") or ""
    loc = job.get("location") or {}
    location = ", ".join(x for x in [loc.get("city"), loc.get("countryName")] if x) or (
        "Remote" if job.get("workplace") == "remote" else None
    )
    description = "\n\n".join(
        _strip_html(x)
        for x in [job.get("description"), job.get("requirementsSection"), job.get("benefitsSection")]
        if x
    ).strip()
    return {
        "external_id": job.get("id", ""),
        "title": job.get("title", "No Title"),
        "company": company,
        "location": location,
        "url": job.get("url", ""),
        "description": description,
        "posted_at": job.get("created"),
    }


def fetch_feed(location: str = "", max_pages: int = 3, max_jobs: int = 300) -> list[dict[str, Any]]:
    """Page the global feed for a location, returning normalized job dicts (company omitted)."""
    out: list[dict[str, Any]] = []
    token: str | None = None
    pages = 0
    while pages < max_pages and len(out) < max_jobs:
        params: dict[str, str] = {}
        if location:
            params["location"] = location
        if token:
            params["token"] = token
        try:
            resp = httpx.get(_FEED, params=params, timeout=_TIMEOUT)
            resp.raise_for_status()
        except httpx.HTTPError:
            break
        data = resp.json()
        out.extend(_normalize(j) for j in data.get("jobs", []) if j.get("company"))
        token = data.get("nextPageToken")
        pages += 1
        if not token:
            break
    return out[:max_jobs]
