"""Scenarios, characters, prompts, images, versions, story runs, events and LLM call log.

Revision ID: 0001
Revises:
Create Date: 2026-09-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())
NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "scenarios",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("subtitle", sa.Text(), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("setting", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("background_image", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="published"),
        sa.Column("settings", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("generated_from", sa.Text(), nullable=True),
        sa.Column("extra", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )

    op.create_table(
        "characters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scenario_id", sa.String(64), sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("goals", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("inventory", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("persona", sa.Text(), nullable=False, server_default=""),
        sa.Column("english_style", sa.Text(), nullable=False, server_default=""),
        sa.Column("appeals", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("review_notes_urdu", sa.Text(), nullable=False, server_default=""),
        sa.Column("review_notes_english", sa.Text(), nullable=False, server_default=""),
        sa.Column("voice", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("image", sa.Text(), nullable=False, server_default=""),
        sa.Column("color", sa.String(16), nullable=False, server_default="slate"),
        sa.UniqueConstraint("scenario_id", "key", name="uq_characters_scenario_key"),
        sa.UniqueConstraint("scenario_id", "name", name="uq_characters_scenario_name"),
    )
    op.create_index("ix_characters_scenario_id", "characters", ["scenario_id"])

    op.create_table(
        "prompts",
        sa.Column("scenario_id", sa.String(64), sa.ForeignKey("scenarios.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("name", sa.String(64), primary_key=True),
        sa.Column("template", sa.Text(), nullable=False),
    )

    op.create_table(
        "images",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scenario_id", sa.String(64), nullable=True),
        sa.Column("filename", sa.Text(), nullable=False, server_default=""),
        sa.Column("content_type", sa.String(64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_index("ix_images_scenario_id", "images", ["scenario_id"])

    op.create_table(
        "scenario_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scenario_id", sa.String(64), sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", JSONB, nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("scenario_id", "version", name="uq_scenario_versions"),
    )
    op.create_index("ix_scenario_versions_scenario_id", "scenario_versions", ["scenario_id"])

    op.create_table(
        "story_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scenario_id", sa.String(64), nullable=False),
        sa.Column("scenario_version", sa.Integer(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("seed", sa.Text(), nullable=False, server_default=""),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("turn_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("action_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("twist_turn", sa.Integer(), nullable=True),
        sa.Column("conclusion", sa.Text(), nullable=False, server_default=""),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("models_used", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("llm_call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("turns", JSONB, nullable=True),
        sa.Column("in_replay_pool", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("times_served", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_served_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(16), nullable=False, server_default="api"),
    )
    op.create_index("ix_story_runs_scenario_id", "story_runs", ["scenario_id"])
    op.create_index("ix_story_runs_status", "story_runs", ["status"])
    op.create_index("ix_story_runs_replay", "story_runs", ["scenario_id", "status", "in_replay_pool"])

    op.create_table(
        "story_events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("story_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("turn", sa.Integer(), nullable=True),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("speaker", sa.Text(), nullable=True),
        sa.Column("character_key", sa.String(64), nullable=True),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("data", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_index("ix_story_events_run_seq", "story_events", ["run_id", "seq"])

    op.create_table(
        "llm_calls",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("story_runs.id", ondelete="CASCADE"), nullable=True),
        sa.Column("agent", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("response", sa.Text(), nullable=False, server_default=""),
        sa.Column("ok", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_index("ix_llm_calls_run_id", "llm_calls", ["run_id"])
    op.create_index("ix_llm_calls_created_at", "llm_calls", ["created_at"])


def downgrade() -> None:
    for table in ("llm_calls", "story_events", "story_runs", "scenario_versions", "images", "prompts",
                  "characters", "scenarios"):
        op.drop_table(table)
