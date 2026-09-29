"""
Database connection (Neon Postgres, async SQLAlchemy + asyncpg).

On startup the schema is brought up to date with Alembic (alembic/versions/). If DATABASE_URL is not set
or the database is unreachable, the app keeps working: stories run without being recorded and scenarios
are read (read-only) from the JSON files in scenarios/.
"""
import asyncio
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent
RECONNECT_INTERVAL = 30  # seconds between reconnect attempts after a failure

_engine: Optional[AsyncEngine] = None
_sessions: Optional[async_sessionmaker] = None
_last_attempt = 0.0


def async_url(url: str) -> tuple[str, dict]:
    """postgresql://...?sslmode=require → postgresql+asyncpg://... with ssl passed as a connect arg."""
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    sslmode = query.pop("sslmode", None)
    query.pop("channel_binding", None)  # not supported by asyncpg
    scheme = "postgresql+asyncpg" if parts.scheme in ("postgres", "postgresql") else parts.scheme
    connect_args = {"ssl": "require"} if sslmode in ("require", "verify-ca", "verify-full") else {}
    return urlunsplit((scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)), connect_args


def enabled() -> bool:
    return _sessions is not None


def _run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    command.upgrade(cfg, "head")


async def init_db(attempts: int = 3) -> None:
    """Connect and migrate. Retries (Neon may be waking up), then disables the database."""
    global _engine, _sessions, _last_attempt
    _last_attempt = time.time()
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        print("[DB] DATABASE_URL not set — running without a database (read-only scenarios, runs not recorded).")
        return
    url, connect_args = async_url(url)
    for attempt in range(1, attempts + 1):
        try:
            await asyncio.to_thread(_run_migrations)
            # Neon drops idle connections; recycle them before that and check each one before use.
            _engine = create_async_engine(url, connect_args={**connect_args, "timeout": 30}, pool_pre_ping=True,
                                          pool_size=5, pool_recycle=240)
            async with _engine.connect():
                pass
            _sessions = async_sessionmaker(_engine, expire_on_commit=False)
            print("[DB] Connected and schema up to date.")
            return
        except Exception as e:
            if _engine is not None:
                await _engine.dispose()
            _engine, _sessions = None, None
            if attempt == attempts:
                print(f"[DB] Could not connect ({e!r}) — running without a database.")
            else:
                await asyncio.sleep(2 * attempt)


async def ensure() -> bool:
    """True if the database is usable; reconnects lazily if it was down."""
    if _sessions is None and os.getenv("DATABASE_URL") and time.time() - _last_attempt > RECONNECT_INTERVAL:
        await init_db(attempts=1)
    return _sessions is not None


@asynccontextmanager
async def session() -> AsyncIterator[AsyncSession]:
    if _sessions is None:
        raise RuntimeError("database is not connected")
    async with _sessions() as s:
        yield s


async def close_db() -> None:
    if _engine is not None:
        await _engine.dispose()


def is_complete(turns: list, conclusion: str) -> bool:
    """A story counts as complete when it has an ending and no failed ('...') turns."""
    if not turns or not (conclusion or "").strip():
        return False
    return all((t.get("dialogue") or "").strip() not in ("", "...") for t in turns)
