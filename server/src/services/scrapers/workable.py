"""Workable scraper. Public JSON API — no token.

fetch_board(account): pull a company's jobs (list + detail).
discover(location): find company account slugs from Workable's global jobs feed —
the "better way to search" than a hand-maintained company list.
"""

import html
import re
from typing import Any

import httpx

_LIST = "https://apply.workable.com/api/v3/accounts/{account}/jobs"
_DETAIL = "https://apply.workable.com/api/v1/accounts/{account}/jobs/{shortcode}"
_DISCOVER = "https://jobs.workable.com/api/v1/jobs"
_TIMEOUT = 30
_MAX_LIST_PAGES = 3
_MAX_DETAIL = 30


def _strip_html(raw: str) -> str:
    text = html.unescape(raw or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_board(account: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    token, pages = None, 0
    while pages < _MAX_LIST_PAGES:
        body: dict[str, Any] = {"query": "", "location": [], "department": [], "workplace": [], "worktype": []}
        if token:
            body["token"] = token
        try:
            resp = httpx.post(_LIST.format(account=account), json=body, timeout=_TIMEOUT)
        except httpx.HTTPError:
            break
        if resp.status_code != 200:
            break
        data = resp.json()
        candidates.extend(data.get("results", []))
        token = data.get("nextPage")
        pages += 1
        if not token:
            break

    out: list[dict[str, Any]] = []
    for c in candidates[:_MAX_DETAIL]:
        shortcode = c.get("shortcode")
        if not shortcode:
            continue
        try:
            detail = httpx.get(_DETAIL.format(account=account, shortcode=shortcode), timeout=_TIMEOUT).json()
        except httpx.HTTPError:
            continue
        description = "\n\n".join(
            _strip_html(x) for x in [detail.get("description"), detail.get("requirements"), detail.get("benefits")] if x
        ).strip()
        loc = c.get("location") or {}
        location = ", ".join(
            x for x in [loc.get("city"), loc.get("region"), loc.get("country")] if x
        ) or ("Remote" if c.get("remote") else None)
        out.append(
            {
                "external_id": shortcode,
                "title": c.get("title", "No Title"),
                "location": location,
                "url": f"https://apply.workable.com/{account}/j/{shortcode}/",
                "description": description,
                "posted_at": c.get("published"),
            }
        )
    return out


def discover(location: str, max_pages: int = 20) -> dict[str, str]:
    """Return {account_slug: company_name} from the global Workable feed for a location."""
    found: dict[str, str] = {}
    token, pages = None, 0
    while pages < max_pages:
        params = {"location": location}
        if token:
            params["token"] = token
        try:
            resp = httpx.get(_DISCOVER, params=params, timeout=_TIMEOUT)
            resp.raise_for_status()
        except httpx.HTTPError:
            break
        data = resp.json()
        for job in data.get("jobs", []):
            url = job.get("url") or job.get("application_url") or ""
            m = re.search(r"workable\.com/(?:api/v\d+/accounts/)?([a-z0-9-]+)", url)
            account = m.group(1) if m else (job.get("company_slug") or "")
            if account and account not in found:
                found[account] = job.get("company_name") or job.get("company") or account
        token = data.get("nextPageToken") or data.get("nextPage")
        pages += 1
        if not token:
            break
    return found
