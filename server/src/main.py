from fastapi import FastAPI

from src.config.settings import settings
from src.routers import resume

app = FastAPI(title=settings.app_name)

app.include_router(resume.router, prefix="/resume", tags=["resume"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
