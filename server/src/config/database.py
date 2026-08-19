from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config.settings import settings

# pool_pre_ping avoids handing out dead connections after Postgres drops idle ones.
engine = create_engine(settings.sqlalchemy_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
