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

## Job sources

Saving preferences and the dashboard's **Refresh jobs** action call one combined operation:
it fetches preference-scoped LinkedIn, Indeed and Naukri jobs through Apify (at most once per
account per UTC day), then matches the available database jobs. Configure `APIFY_TOKEN` on the
web service to enable fresh-job fetching. Indeed and Naukri default to six title/location
queries with ten results per query per source.

The repository does not currently bundle a scheduled workflow. To ingest the free Greenhouse,
Lever and Workable sources as a batch, schedule `pipenv run python -m src.jobs.fetch_jobs` in
the deployment environment.

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
