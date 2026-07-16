import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config.settings import settings
from src.routers import profile, resume

logging.basicConfig(level=logging.INFO)

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(resume.router, prefix="/resume", tags=["resume"])
app.include_router(profile.router, prefix="/profile", tags=["profile"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
