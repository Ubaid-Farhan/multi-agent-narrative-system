"""
Records every story run in the database, step by step, while it happens:

  story_runs    one row per run (the run number), status, counts, ending, models used
  story_events  every step in order — director narration, twist, dialogue (+ reasoning), rejected drafts,
                reviewer verdicts, actions, world state, conclusion checks, the ending, errors
  llm_calls     every prompt/response with model and latency (LLM_LOG_ENABLED, kept LLM_LOG_RETENTION_DAYS)

Writes go through a queue drained by a background task, so recording never slows a story down and a
database hiccup never breaks one. Also: picking a saved run to replay, and the admin "Stories" queries.
"""
import asyncio
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, func, select, update

from . import db
from .models import LlmCall, StoryEvent, StoryRun

LLM_LOG_ENABLED = os.getenv("LLM_LOG_ENABLED", "true").strip().lower() not in ("0", "false", "no", "off")
LLM_LOG_RETENTION_DAYS = int(os.getenv("LLM_LOG_RETENTION_DAYS", "30"))
FINAL_STATUSES = ("completed", "incomplete", "failed", "aborted")


def _jsonable(value: Any) -> Any:
    """Make world-state / metadata safe for JSONB."""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _copy_row(row):
    """A fresh ORM object with the same values (a failed session leaves the original unusable)."""
    cls = type(row)
    return cls(**{c.name: getattr(row, c.name) for c in cls.__table__.columns if getattr(row, c.name) is not None})


class RunRecorder:
    """One per story run. All methods are safe to call when the database is off (they do nothing)."""

    def __init__(self, scenario: Dict, language: str, source: str = "api"):
        self.scenario = scenario
        self.language = language
        self.source = source
        self.run_id: Optional[int] = None
        self._seq = 0
        self._queue: Optional[asyncio.Queue] = None
        self._worker: Optional[asyncio.Task] = None
        self._finished = False
        self.models_used: List[str] = []
        self.llm_call_count = 0
        self.twist_turn: Optional[int] = None
        self.keys = {c["name"]: c.get("key") for c in scenario.get("characters", [])}

    @property
    def active(self) -> bool:
        return self.run_id is not None

    async def start(self) -> Optional[int]:
        if not await db.ensure():
            return None
        try:
            async with db.session() as s, s.begin():
                run = StoryRun(scenario_id=self.scenario["id"], scenario_version=self.scenario.get("version"),
                               title=self.scenario.get("title") or "", seed=self.scenario.get("description") or "",
                               language=self.language, status="running", source=self.source)
                s.add(run)
            self.run_id = run.id
        except Exception as e:
            print(f"[Recorder] Could not start a run record: {e!r}")
            return None
        self._queue = asyncio.Queue()
        self._worker = asyncio.create_task(self._drain())
        print(f"[Recorder] Run #{self.run_id} started ({self.scenario['id']}, {self.language})")
        return self.run_id

    # ── recording (non-blocking) ──

    def event(self, type: str, *, turn: Optional[int] = None, speaker: Optional[str] = None,
              content: str = "", **data) -> None:
        if not self.active or self._finished:
            return
        self._seq += 1
        if type == "twist":
            self.twist_turn = turn
        self._queue.put_nowait(StoryEvent(
            run_id=self.run_id, seq=self._seq, turn=turn, type=type, speaker=speaker,
            character_key=self.keys.get(speaker) if speaker else None,
            content=content or "", data=_jsonable({k: v for k, v in data.items() if v is not None})))

    def llm_call(self, agent: str, model: Optional[str], prompt: str, response: str, ok: bool,
                 error: Optional[str] = None, latency_ms: Optional[int] = None) -> None:
        if model and model not in self.models_used:
            self.models_used.append(model)
        self.llm_call_count += 1
        if not self.active or self._finished or not LLM_LOG_ENABLED:
            return
        self._queue.put_nowait(LlmCall(run_id=self.run_id, agent=agent, model=model, prompt=prompt or "",
                                       response=response or "", ok=ok, error=error, latency_ms=latency_ms))

    async def _drain(self) -> None:
        """Write queued rows in order, batching whatever has piled up."""
        while True:
            item = await self._queue.get()
            if item is None:
                self._queue.task_done()
                return
            batch = [item]
            stop = False
            while not self._queue.empty() and len(batch) < 100:
                nxt = self._queue.get_nowait()
                if nxt is None:
                    stop = True
                    break
                batch.append(nxt)
            for attempt in range(3):  # a dropped connection is retried on a fresh one
                try:
                    async with db.session() as s, s.begin():
                        s.add_all([_copy_row(row) for row in batch])
                    break
                except Exception as e:
                    if attempt == 2:
                        print(f"[Recorder] Could not write {len(batch)} rows for run #{self.run_id}: {e!r}")
                    else:
                        await asyncio.sleep(1 + 2 * attempt)
            for _ in batch:
                self._queue.task_done()
            if stop:
                self._queue.task_done()
                return

    async def finish(self, status: str, *, turns: Optional[list] = None, conclusion: str = "",
                     error: Optional[str] = None, turn_count: int = 0, action_count: int = 0) -> None:
        """Flush all events and close the run. `completed` runs join the replay pool."""
        if not self.active or self._finished:
            return
        self._finished = True
        try:
            self._queue.put_nowait(None)
            await asyncio.wait_for(self._worker, timeout=60)
        except Exception as e:
            print(f"[Recorder] Flush for run #{self.run_id} did not finish: {e!r}")
        try:
            async with db.session() as s, s.begin():
                await s.execute(update(StoryRun).where(StoryRun.id == self.run_id).values(
                    status=status, finished_at=datetime.now(timezone.utc), turns=turns, conclusion=conclusion or "",
                    error=error, turn_count=turn_count, action_count=action_count, twist_turn=self.twist_turn,
                    models_used=self.models_used, llm_call_count=self.llm_call_count,
                    in_replay_pool=(status == "completed")))
            print(f"[Recorder] Run #{self.run_id} {status} ({turn_count} turns, {self.llm_call_count} LLM calls)")
        except Exception as e:
            print(f"[Recorder] Could not close run #{self.run_id}: {e!r}")


async def log_llm_call(agent: str, model: Optional[str], prompt: str, response: str, ok: bool,
                       error: Optional[str] = None, latency_ms: Optional[int] = None) -> None:
    """Log an LLM call that isn't part of a story run (e.g. the scenario generator)."""
    if not LLM_LOG_ENABLED or not db.enabled():
        return
    try:
        async with db.session() as s, s.begin():
            s.add(LlmCall(run_id=None, agent=agent, model=model, prompt=prompt or "", response=response or "",
                          ok=ok, error=error, latency_ms=latency_ms))
    except Exception as e:
        print(f"[Recorder] Could not log LLM call: {e!r}")


# ─────────────────────────────── maintenance ───────────────────────────────

async def close_stale_runs() -> int:
    """Runs still 'running' after a server restart can never finish — mark them aborted."""
    if not db.enabled():
        return 0
    async with db.session() as s, s.begin():
        result = await s.execute(update(StoryRun).where(StoryRun.status == "running").values(
            status="aborted", finished_at=datetime.now(timezone.utc), error="Server restarted during the run"))
    return result.rowcount or 0


async def cleanup_llm_calls(days: int = LLM_LOG_RETENTION_DAYS) -> int:
    if not db.enabled():
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    async with db.session() as s, s.begin():
        result = await s.execute(delete(LlmCall).where(LlmCall.created_at < cutoff))
    return result.rowcount or 0


# ─────────────────────────────── replay ───────────────────────────────

async def pick_replay(scenario_id: str, language: str) -> Optional[Dict]:
    """A completed run to replay: same language preferred, least-shown first (random among ties)."""
    if not await db.ensure():
        return None
    try:
        async with db.session() as s, s.begin():
            base = [StoryRun.scenario_id == scenario_id, StoryRun.status == "completed",
                    StoryRun.in_replay_pool.is_(True), StoryRun.turns.is_not(None)]
            for extra in ([StoryRun.language == language], []):
                where = base + extra
                least = (await s.execute(select(func.min(StoryRun.times_served)).where(*where))).scalar()
                if least is None:
                    continue
                rows = (await s.execute(select(StoryRun).where(*where, StoryRun.times_served == least))).scalars().all()
                run = random.choice(rows)
                run.times_served += 1
                run.last_served_at = datetime.now(timezone.utc)
                return {"id": run.id, "title": run.title, "scenario": run.seed, "turns": run.turns,
                        "conclusion": run.conclusion, "language": run.language}
    except Exception as e:
        print(f"[Replay] Could not load a saved run: {e!r}")
    return None


# ─────────────────────────────── admin queries ───────────────────────────────

RUN_LIST_COLUMNS = ("id", "scenario_id", "scenario_version", "title", "language", "status", "started_at",
                    "finished_at", "turn_count", "action_count", "twist_turn", "models_used", "llm_call_count",
                    "in_replay_pool", "times_served", "last_served_at", "source", "error")


def _run_summary(run: StoryRun) -> Dict:
    out = {}
    for col in RUN_LIST_COLUMNS:
        value = getattr(run, col)
        out[col] = value.isoformat() if isinstance(value, datetime) else value
    if run.started_at and run.finished_at:
        out["duration_seconds"] = int((run.finished_at - run.started_at).total_seconds())
    return out


async def list_runs(scenario_id: Optional[str] = None, status: Optional[str] = None,
                    language: Optional[str] = None, limit: int = 50, offset: int = 0) -> Dict:
    filters = []
    if scenario_id:
        filters.append(StoryRun.scenario_id == scenario_id)
    if status:
        filters.append(StoryRun.status == status)
    if language:
        filters.append(StoryRun.language == language)
    async with db.session() as s:
        total = (await s.execute(select(func.count()).select_from(StoryRun).where(*filters))).scalar()
        runs = (await s.execute(select(StoryRun).where(*filters).order_by(StoryRun.id.desc())
                                .limit(min(max(limit, 1), 200)).offset(max(offset, 0)))).scalars().all()
        counts = dict((await s.execute(select(StoryRun.status, func.count()).group_by(StoryRun.status))).all())
    return {"runs": [_run_summary(r) for r in runs], "total": total, "status_counts": counts}


async def get_run(run_id: int) -> Optional[Dict]:
    async with db.session() as s:
        run = await s.get(StoryRun, run_id)
        if run is None:
            return None
        events = (await s.execute(select(StoryEvent).where(StoryEvent.run_id == run_id)
                                  .order_by(StoryEvent.seq))).scalars().all()
    return {**_run_summary(run), "seed": run.seed, "conclusion": run.conclusion, "turns": run.turns,
            "events": [{"seq": e.seq, "turn": e.turn, "type": e.type, "speaker": e.speaker,
                        "character_key": e.character_key, "content": e.content, "data": e.data,
                        "created_at": e.created_at.isoformat()} for e in events]}


async def get_llm_calls(run_id: int) -> List[Dict]:
    async with db.session() as s:
        calls = (await s.execute(select(LlmCall).where(LlmCall.run_id == run_id).order_by(LlmCall.id))).scalars().all()
    return [{"id": c.id, "agent": c.agent, "model": c.model, "prompt": c.prompt, "response": c.response,
             "ok": c.ok, "error": c.error, "latency_ms": c.latency_ms, "created_at": c.created_at.isoformat()}
            for c in calls]


async def set_replay_pool(run_id: int, in_pool: bool) -> bool:
    async with db.session() as s, s.begin():
        result = await s.execute(update(StoryRun).where(StoryRun.id == run_id).values(in_replay_pool=in_pool))
    return bool(result.rowcount)


async def delete_run(run_id: int) -> bool:
    async with db.session() as s, s.begin():
        result = await s.execute(delete(StoryRun).where(StoryRun.id == run_id))
    return bool(result.rowcount)
