from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Tailr API"
    environment: str = "development"

    database_url: str = ""

    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7

    anthropic_api_key: str = ""
    openai_api_key: str = ""

    max_upload_bytes: int = 5 * 1024 * 1024

    # LinkedIn scraping via Apify — CRON ONLY. Token from env (never hardcode).
    apify_token: str = ""
    apify_actor_id: str = "curious_coder~linkedin-jobs-scraper"
    apify_location: str = "India"
    apify_count: int = 10  # results per search title (quota control)
    apify_max_titles: int = 10  # cap distinct title searches per run

    # Workable global-feed discovery (free, no token). Bounds keep /jobs/refresh snappy.
    workable_max_pages: int = 3       # feed pages per location (~100 jobs/page)
    workable_max_locations: int = 3   # distinct user locations queried per run

    @property
    def sqlalchemy_url(self) -> str:
        # Managed Postgres (Render/Supabase) hands out postgres:// or postgresql:// URLs,
        # which SQLAlchemy maps to psycopg2. Force our installed psycopg3 driver.
        url = self.database_url
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
