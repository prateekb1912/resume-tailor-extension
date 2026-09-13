"""Indeed job discovery through one batched invocation of a configurable Apify Actor."""

import html
import logging
import re
from typing import Any
from urllib.parse import urlencode

import httpx

from src.config.enums import JobSource

_RUN_SYNC = "https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items?token={token}"
_TIMEOUT = 360
logger = logging.getLogger(__name__)


def _text(value: Any) -> str:
    raw = html.unescape(str(value or ""))
    raw = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def _indeed_domain(country: str) -> str:
    code = country.strip().lower()
    if code == "us":
        return "www.indeed.com"
    if code == "gb":
        return "uk.indeed.com"
    return f"{code}.indeed.com"


def _search_url(title: str, location: str, country: str) -> str:
    query = urlencode({"q": title, "l": location, "fromage": 7, "sort": "date"})
    return f"https://{_indeed_domain(country)}/jobs?{query}"


def _canonical(job: dict[str, Any], country: str) -> str:
    job_id = str(job.get("id") or job.get("jobKey") or "").strip()
    if job_id:
        return f"https://{_indeed_domain(country)}/viewjob?jk={job_id}"
    return str(job.get("url") or job.get("jobUrl") or "").strip()


def fetch_jobs(
    queries: list[tuple[str, str]],
    token: str,
    actor_id: str,
    country: str,
    count: int,
) -> list[dict[str, Any]]:
    if not queries:
        return []

    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    # The Actor accepts many search URLs in one input. Keep the title/location coverage while
    # avoiding one paid Actor startup for every query in the preference cross-product.
    body = {
        "startUrls": [
            {"url": _search_url(title, location, country)} for title, location in queries
        ],
        "maxItemsPerSearch": count,
        "parseCompanyDetails": False,
        "saveOnlyUniqueItems": True,
        "followApplyRedirects": False,
    }
    try:
        response = httpx.post(
            _RUN_SYNC.format(actor=actor_id, token=token),
            json=body,
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001 — skip Indeed, let other sources continue
        logger.warning("Indeed batch failed for %s queries: %s", len(queries), exc)
        return []

    for job in response.json():
        url = _canonical(job, country)
        external_id = str(job.get("id") or job.get("jobKey") or url).strip()
        identity = external_id or url
        if not identity or identity in seen:
            continue
        description = _text(
            job.get("description")
            or job.get("descriptionText")
            or job.get("jobDescription")
        )
        if len(description) < 50:
            continue
        seen.add(identity)
        out.append(
            {
                "source": JobSource.INDEED,
                "external_id": external_id,
                "title": job.get("positionName") or job.get("title") or "",
                "company": job.get("company") or job.get("companyName") or "",
                "location": job.get("location"),
                "url": url,
                "description": description,
                "posted_at": job.get("postingDateParsed") or job.get("postedAt"),
            }
        )
    return out
