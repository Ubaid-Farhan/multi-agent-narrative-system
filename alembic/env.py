"""Alembic environment: async engine from DATABASE_URL, serialised with a Postgres advisory lock."""
import asyncio
import os

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.db import async_url
from src.models import Base

load_dotenv()
config = context.config
target_metadata = Base.metadata
MIGRATION_LOCK_ID = 728_391_004  # any constant; stops two servers migrating at the same time


def _url() -> tuple[str, dict]:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return async_url(url)


def run_migrations_offline() -> None:
    context.configure(url=_url()[0], target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    url, connect_args = _url()
    engine = create_async_engine(url, connect_args=connect_args)
    async with engine.connect() as connection:
        await connection.execute(text(f"SELECT pg_advisory_lock({MIGRATION_LOCK_ID})"))
        try:
            await connection.run_sync(_do_run_migrations)
            await connection.commit()
        finally:
            await connection.execute(text(f"SELECT pg_advisory_unlock({MIGRATION_LOCK_ID})"))
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
