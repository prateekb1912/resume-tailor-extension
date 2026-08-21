"""Naukri job discovery through a configurable Apify Actor.

This is a paid scheduled source. It is intentionally not called by an interactive API route.
"""

import html
import logging
import re
from datetime import datetime, timezone
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


def _url(job: dict[str, Any]) -> str:
    value = str(job.get("jdURL") or job.get("url") or "").strip()
    if value.startswith("/"):
        return "https://www.naukri.com" + value
    return value


def _posted_at(job: dict[str, Any]) -> str | None:
    value = job.get("createdDate")
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()
    return job.get("postedDate")


def _description(job: dict[str, Any]) -> str:
    parts = [_text(job.get("jobDescription") or job.get("description"))]
    skills = job.get("tagsAndSkills") or job.get("skills") or []
    if isinstance(skills, str):
        skills = [skills]
    if skills:
        parts.append("Skills: " + ", ".join(_text(skill) for skill in skills if skill))
    experience = _text(job.get("experienceLabel") or job.get("experience"))
    if experience:
        parts.append("Experience: " + experience)
    return "\n".join(part for part in parts if part)


def fetch_jobs(
    queries: list[tuple[str, str]], token: str, actor_id: str, count: int
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    for title, location in queries:
        body = {
            "keyword": title,
            "location": location,
            "jobAge": "7",
            "sort": "date",
            "maxResultsPerQuery": count,
            "fetchAdditionalDetails": False,
        }
        try:
            response = httpx.post(
                _RUN_SYNC.format(actor=actor_id, token=token),
                json=body,
                timeout=_TIMEOUT,
            )
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001 — skip one failed query, keep the daily run
            logger.warning("Naukri query failed for %s / %s: %s", title, location, exc)
            continue

        for job in response.json():
            url = _url(job)
            external_id = str(job.get("jobId") or url).strip()
            identity = external_id or url
            if not identity or identity in seen:
                continue
            description = _description(job)
            if len(description) < 50:
                continue
            seen.add(identity)
            out.append(
                {
                    "source": JobSource.NAUKRI,
                    "external_id": external_id,
                    "title": job.get("title") or "",
                    "company": job.get("companyName") or job.get("company") or "",
                    "location": job.get("locationLabel") or job.get("location"),
                    "url": url,
                    "description": description,
                    "posted_at": _posted_at(job),
                }
            )
    return out
