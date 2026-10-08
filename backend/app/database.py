from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def normalize_database_url(url: str) -> str:
    if url.startswith(("postgres://", "postgresql://")):
        return url.replace(url.split("://", 1)[0] + "://", "postgresql+psycopg://", 1)
    return url


def build_engine():
    settings = get_settings()
    url = normalize_database_url(settings.database_url)

    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {
        "connect_timeout": settings.db_connect_timeout_seconds
    }
    engine_options = {
        "pool_pre_ping": True,
        "connect_args": connect_args,
    }
    if not url.startswith("sqlite"):
        engine_options.update({
            "pool_size": settings.db_pool_size,
            "max_overflow": settings.db_max_overflow,
            "pool_timeout": settings.db_pool_timeout_seconds,
            "pool_recycle": settings.db_pool_recycle_seconds,
        })
    return create_engine(url, **engine_options)


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
