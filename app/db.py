import asyncio
import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import db_env_debug, on_railway, settings

log = logging.getLogger("sentinel.db")


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.async_database_url(),
    pool_pre_ping=True,
    connect_args=settings.database_connect_args(),
)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    from app import models  # noqa: F401

    log.info("Postgres target %s | %s", settings.database_host_for_log(), db_env_debug())
    if on_railway() and "localhost" in (settings.database_host_for_log() or ""):
        raise RuntimeError(
            "DATABASE_URL still points to localhost. In Railway open bank_ai_manager → "
            "Variables, delete DATABASE_URL if it contains localhost, then Add Variable "
            "Reference from the Postgres service: DATABASE_PRIVATE_URL or DATABASE_URL. "
            f"Now: {db_env_debug()}"
        )

    last_error: Exception | None = None
    for attempt in range(1, 16):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            log.info("Postgres ready at %s", settings.database_host_for_log())
            return
        except Exception as exc:
            last_error = exc
            log.warning(
                "Postgres not ready (%s) attempt %s/15: %s",
                settings.database_host_for_log(),
                attempt,
                exc,
            )
            await asyncio.sleep(2)
    raise RuntimeError(
        f"Cannot connect to Postgres at {settings.database_host_for_log()}. "
        f"{db_env_debug()}. On Railway: share Postgres DATABASE_PRIVATE_URL into this service."
    ) from last_error
