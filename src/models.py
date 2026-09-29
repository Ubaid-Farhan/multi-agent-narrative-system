"""
Database tables (Neon Postgres). Schema changes go through Alembic migrations in alembic/versions/.

Admin panel data:   scenarios, characters, prompts, images, scenario_versions
Story runs:         story_runs (one row per run = the "run number"), story_events (every step of a run),
                    llm_calls (every prompt/response, auto-deleted after LLM_LOG_RETENTION_DAYS)
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text,
                        UniqueConstraint, func)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _now():
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ─────────────────────────────── admin panel data ───────────────────────────────

class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    subtitle: Mapped[str] = mapped_column(Text, default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    setting: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    background_image: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="published", nullable=False)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    generated_from: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)  # any other top-level keys
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now(), nullable=False)


class Character(Base):
    __tablename__ = "characters"
    __table_args__ = (
        UniqueConstraint("scenario_id", "key", name="uq_characters_scenario_key"),
        UniqueConstraint("scenario_id", "name", name="uq_characters_scenario_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"), index=True, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    goals: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    inventory: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    persona: Mapped[str] = mapped_column(Text, default="", nullable=False)
    english_style: Mapped[str] = mapped_column(Text, default="", nullable=False)
    appeals: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    review_notes_urdu: Mapped[str] = mapped_column(Text, default="", nullable=False)
    review_notes_english: Mapped[str] = mapped_column(Text, default="", nullable=False)
    voice: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    image: Mapped[str] = mapped_column(Text, default="", nullable=False)
    color: Mapped[str] = mapped_column(String(16), default="slate", nullable=False)


class Prompt(Base):
    __tablename__ = "prompts"

    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    template: Mapped[str] = mapped_column(Text, nullable=False)


class Image(Base):
    """Image bytes stored in the database; served at /api/images/<id>. Identical files are stored once."""
    __tablename__ = "images"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scenario_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)  # who uploaded it
    filename: Mapped[str] = mapped_column(Text, default="", nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = _now()


class ScenarioVersion(Base):
    """Full snapshot of a scenario at every save, for history and restore."""
    __tablename__ = "scenario_versions"
    __table_args__ = (UniqueConstraint("scenario_id", "version", name="uq_scenario_versions"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = _now()


# ─────────────────────────────── story runs ───────────────────────────────

class StoryRun(Base):
    """One row per story run. `id` is the run number."""
    __tablename__ = "story_runs"
    __table_args__ = (Index("ix_story_runs_replay", "scenario_id", "status", "in_replay_pool"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scenario_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # kept even if scenario is deleted
    scenario_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(Text, default="", nullable=False)
    seed: Mapped[str] = mapped_column(Text, default="", nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    # running → completed | incomplete (ended with failed turns / no ending) | failed (error) | aborted (viewer left)
    status: Mapped[str] = mapped_column(String(16), default="running", index=True, nullable=False)
    started_at: Mapped[datetime] = _now()
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    turn_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    action_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    twist_turn: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    conclusion: Mapped[str] = mapped_column(Text, default="", nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    models_used: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    llm_call_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    turns: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)  # player-shaped turns, for replay
    in_replay_pool: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    times_served: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_served_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="api", nullable=False)  # api | cli | imported
    # Full story state after the last saved turn (memories, world state, events…) so an unfinished run can be
    # continued. Cleared once the story has an ending.
    state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    resumed_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)


class StoryEvent(Base):
    """Every step of a run, in order: narration, twist, dialogue (+reasoning), review, action, world state…"""
    __tablename__ = "story_events"
    __table_args__ = (Index("ix_story_events_run_seq", "run_id", "seq"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("story_runs.id", ondelete="CASCADE"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    turn: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    speaker: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    character_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = _now()


class LlmCall(Base):
    """Every LLM prompt and response (story agents and the scenario generator)."""
    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("story_runs.id", ondelete="CASCADE"), index=True, nullable=True)
    agent: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    response: Mapped[str] = mapped_column(Text, default="", nullable=False)
    ok: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True,
                                                 nullable=False)
