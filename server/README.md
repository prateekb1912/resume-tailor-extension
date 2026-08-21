# Tailr — Server

FastAPI backend. Python 3.11+, managed with [uv](https://docs.astral.sh/uv/).

## Setup

```bash
cd server
uv sync                 # create venv + install deps
cp .env.example .env    # then fill in secrets
```

## Run

```bash
uv run uvicorn src.main:app --reload
```

Health check: `GET http://127.0.0.1:8000/health` → `{"status": "ok"}`.

## Tests

```bash
uv run pytest tests/ -v
```

## Lint

```bash
uv run ruff check src/
```

## Scheduled job sources

The GitHub Actions fetch workflow runs Greenhouse, Lever and Workable every six hours. Its
daily run also fetches LinkedIn, Indeed and Naukri through Apify. Configure `APIFY_TOKEN` as
a GitHub Actions secret. Indeed and Naukri default to six title/location queries with ten
results per query per source. Set the optional `APIFY_AGGREGATOR_*` GitHub repository variables
to change those caps, or the actor-ID variables if either community Actor is replaced. Paid
sources are one grouped workflow option; no scraper controls are shown in the web dashboard.

## LLM observability

Every parse, preference-inference, tailoring and job-screening call emits structured JSON at
INFO level with `event=llm_run`, a run ID, operation, provider/model, safe profile/job IDs,
duration, status and provider token usage when available. Prompt, résumé and job-description
contents are deliberately excluded. View API calls in Render service logs and scheduled matching
calls in the corresponding GitHub Actions run; filter either log stream for `"event": "llm_run"`.
Each matching batch also emits `event=match_run`; its `match_run_id` is copied into all associated
job-screen logs so one click or scheduled batch can be traced end-to-end.

## Structure

```
src/
  api/          # route handlers only, no business logic
  services/     # business logic (LLM chains, tailor pipeline)
  repositories/ # db queries, no logic
  models/       # SQLAlchemy models
  schemas/      # Pydantic schemas
  config/       # settings, env, constants
tests/
  unit/
  integration/
```
