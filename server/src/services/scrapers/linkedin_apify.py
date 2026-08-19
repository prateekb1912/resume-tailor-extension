"""LinkedIn scraper via Apify. CRON ONLY — each run consumes Apify quota, so this must
never be wired to an interactive button. Token comes from settings (env)."""

import html
import re
from typing import Any
from urllib.parse import quote

import httpx

from src.config.enums import JobSource

# run-sync-get-dataset-items blocks until the actor finishes and returns items directly.
_RUN_SYNC = "https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items?token={token}"
_SEARCH_URL = (
    "https://www.linkedin.com/jobs/search/?keywords={kw}&location={loc}&f_TPR=r86400&sortBy=DD"
)
_TIMEOUT = 300


def _canonical(url: str) -> str:
    if not url:
        return ""
    m = re.search(r"/jobs/view/(?:[^/?#]*-)?(\d+)", url)
    return f"https://www.linkedin.com/jobs/view/{m.group(1)}" if m else url.split("?")[0]


def _strip_html(raw: str) -> str:
    text = html.unescape(raw or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_jobs(
    titles: list[str], location: str, token: str, actor_id: str, count: int
) -> list[dict[str, Any]]:
    urls = [_SEARCH_URL.format(kw=quote(t), loc=quote(location)) for t in titles]
    body = {"urls": urls, "count": count, "scrapeCompany": False}

    resp = httpx.post(
        _RUN_SYNC.format(actor=actor_id, token=token), json=body, timeout=_TIMEOUT
    )
    resp.raise_for_status()
    items = resp.json()

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for j in items:
        link = _canonical(j.get("link") or j.get("jobUrl") or j.get("url") or "")
        if not link or link in seen:
            continue
        description = _strip_html(j.get("descriptionHtml") or j.get("descriptionText") or "")
        if len(description) < 50:
            continue
        seen.add(link)
        external_id = (re.search(r"/jobs/view/(\d+)", link) or [None, link])[1]
        out.append(
            {
                "source": JobSource.LINKEDIN,
                "external_id": str(external_id),
                "title": j.get("title") or "No Title",
                "company": j.get("companyName") or "Unknown Company",
                "location": j.get("location"),
                "url": link,
                "description": description,
                "posted_at": j.get("postedAt"),
            }
        )
    return out
