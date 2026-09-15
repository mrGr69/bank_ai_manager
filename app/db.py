import asyncio
import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

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
        "On Railway: add a Postgres service and bind DATABASE_URL to this app."
    ) from last_error
