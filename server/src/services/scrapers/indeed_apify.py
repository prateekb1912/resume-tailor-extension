"""Indeed job discovery through a configurable Apify Actor.

This is a paid scheduled source. It is intentionally not called by an interactive API route.
"""

import html
import logging
import re
from typing import Any

import httpx

from src.config.enums import JobSource

_RUN_SYNC = "https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items?token={token}"
_TIMEOUT = 360
logger = logging.getLogger(__name__)


def _text(value: Any) -> str:
    raw = html.unescape(str(value or ""))
    raw = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def _canonical(job: dict[str, Any]) -> str:
    job_id = str(job.get("id") or job.get("jobKey") or "").strip()
    if job_id:
        return f"https://in.indeed.com/viewjob?jk={job_id}"
    return str(job.get("url") or job.get("jobUrl") or "").strip()


def fetch_jobs(
    queries: list[tuple[str, str]],
    token: str,
    actor_id: str,
    country: str,
    count: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    for title, location in queries:
        body = {
            "position": title,
            "location": location,
            "country": country,
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
        except Exception as exc:  # noqa: BLE001 — skip one failed query, keep the daily run
            logger.warning("Indeed query failed for %s / %s: %s", title, location, exc)
            continue

        for job in response.json():
            url = _canonical(job)
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
