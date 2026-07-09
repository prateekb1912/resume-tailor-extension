# Resume Tailor — Server

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
