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

    match_workers: int = 8  # concurrent LLM screens per matching run

    # Comma-separated allowed CORS origins. "*" = allow all (dev). In prod set this to the
    # extension origin, e.g. "chrome-extension://<published-id>". The dashboard is same-origin
    # (served by this app), so it never needs listing here.
    cors_origins: str = "*"

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        return origins or ["*"]

    # LinkedIn scraping via Apify — CRON ONLY. Token from env (never hardcode).
    apify_token: str = ""
    apify_actor_id: str = "curious_coder~linkedin-jobs-scraper"
    apify_location: str = "India"
    apify_count: int = 10  # results per search title (quota control)
    apify_max_titles: int = 10  # cap distinct title searches per run

    # Indeed + Naukri paid Apify sources. These run only in the daily scheduled job or
    # an explicitly requested workflow dispatch. Query and result caps bound spend.
    apify_indeed_actor_id: str = "crawlerbros~indeed-jobs-scraper"
    apify_naukri_actor_id: str = "epicscrapers~naukri-scraper"
    apify_indeed_country: str = "IN"
    apify_aggregator_count: int = 10
    apify_aggregator_max_queries: int = 6

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
