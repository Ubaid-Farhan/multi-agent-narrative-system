"""
Saved stories (Neon Postgres). Every completed story is stored exactly as the player shows it,
so it can be replayed as-is when the LLM is unavailable (API key failed / quota exhausted).
If DATABASE_URL is not set or the database is unreachable, the app keeps working without it.
"""
import asyncio
import os
import random
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv
from sqlalchemy import DateTime, Integer, String, Text, func, select, true, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


load_dotenv()


class Base(DeclarativeBase):
    pass


class SavedStory(Base):
    __tablename__ = "stories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scenario_id: Mapped[str] = mapped_column(String(64), index=True)
    language: Mapped[str] = mapped_column(String(16), index=True)
    title: Mapped[str] = mapped_column(Text, default="")
    scenario_text: Mapped[str] = mapped_column(Text, default="")
    turns: Mapped[list] = mapped_column(JSONB)
    conclusion: Mapped[str] = mapped_column(Text, default="")
    turn_count: Mapped[int] = mapped_column(Integer, default=0)
    times_served: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_served_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


_engine: Optional[AsyncEngine] = None
_sessions: Optional[async_sessionmaker] = None


def _async_url(url: str) -> tuple[str, dict]:
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


_last_attempt = 0.0
RECONNECT_INTERVAL = 30  # seconds between reconnect attempts after a failure


async def init_db(attempts: int = 3) -> None:
    """Connect and create the table if needed. Retries (Neon may be waking up), then disables storage."""
    global _engine, _sessions, _last_attempt
    _last_attempt = time.time()
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        print("[DB] DATABASE_URL not set — stories will not be saved.")
        return
    async_url, connect_args = _async_url(url)
    for attempt in range(1, attempts + 1):
        try:
            _engine = create_async_engine(async_url, connect_args=connect_args, pool_pre_ping=True, pool_size=5)
            async with _engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            _sessions = async_sessionmaker(_engine, expire_on_commit=False)
            print("[DB] Connected — completed stories will be saved.")
            return
        except Exception as e:
            await _engine.dispose()
            _engine, _sessions = None, None
            if attempt == attempts:
                print(f"[DB] Could not connect ({e!r}) — stories will not be saved.")
            else:
                await asyncio.sleep(2 * attempt)


async def _ensure() -> bool:
    """Reconnect lazily if the database was down at startup."""
    if _sessions is None and os.getenv("DATABASE_URL") and time.time() - _last_attempt > RECONNECT_INTERVAL:
        await init_db(attempts=1)
    return _sessions is not None


async def close_db() -> None:
    if _engine is not None:
        await _engine.dispose()


def is_complete(turns: list, conclusion: str) -> bool:
    """Only save a story that finished properly: has an ending and no failed ('...') turns."""
    if not turns or not (conclusion or "").strip():
        return False
    return all((t.get("dialogue") or "").strip() not in ("", "...") for t in turns)


async def save_story(scenario_id: str, language: str, story: dict) -> Optional[int]:
    """Save a completed story. Returns its id, or None if not saved."""
    if not is_complete(story.get("turns", []), story.get("conclusion", "")) or not await _ensure():
        return None
    try:
        async with _sessions() as session:
            row = SavedStory(
                scenario_id=scenario_id,
                language=language,
                title=story.get("title") or "",
                scenario_text=story.get("scenario") or "",
                turns=story["turns"],
                conclusion=story.get("conclusion") or "",
                turn_count=len(story["turns"]),
            )
            session.add(row)
            await session.commit()
            print(f"[DB] Saved story #{row.id} ({scenario_id}, {language}, {row.turn_count} turns)")
            return row.id
    except Exception as e:
        print(f"[DB] Could not save story: {e}")
        return None


async def pick_story(scenario_id: str, language: str) -> Optional[dict]:
    """Pick a saved story to replay: least-shown first (random among ties), same language preferred."""
    if not await _ensure():
        return None
    try:
        async with _sessions() as session:
            for lang_filter in (SavedStory.language == language, true()):
                base = select(SavedStory).where(SavedStory.scenario_id == scenario_id, lang_filter)
                least = (await session.execute(
                    select(func.min(SavedStory.times_served)).where(SavedStory.scenario_id == scenario_id, lang_filter)
                )).scalar()
                if least is None:
                    continue
                rows = (await session.execute(base.where(SavedStory.times_served == least))).scalars().all()
                row = random.choice(rows)
                await session.execute(
                    update(SavedStory).where(SavedStory.id == row.id).values(
                        times_served=SavedStory.times_served + 1, last_served_at=datetime.now(timezone.utc))
                )
                await session.commit()
                return {
                    "id": row.id,
                    "title": row.title,
                    "scenario": row.scenario_text,
                    "turns": row.turns,
                    "conclusion": row.conclusion,
                    "language": row.language,
                }
    except Exception as e:
        print(f"[DB] Could not load a saved story: {e}")
    return None
