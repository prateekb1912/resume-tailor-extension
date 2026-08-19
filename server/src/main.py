import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.config.settings import settings
from src.routers import auth, jobs, profile, resume

logging.basicConfig(level=logging.INFO)

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(resume.router, prefix="/resume", tags=["resume"])
app.include_router(profile.router, prefix="/profile", tags=["profile"])
app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])

# Kanban dashboard served at /app  (same origin as the API -> no CORS needed)
_FRONTEND = Path(__file__).parent.parent / "frontend"
app.mount("/app", StaticFiles(directory=str(_FRONTEND), html=True), name="frontend")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
