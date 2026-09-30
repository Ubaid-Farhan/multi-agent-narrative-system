"""
Bring existing data into the database (runs automatically on API startup; safe to run again):

  1. Every scenarios/<id>/scenario.json that isn't in the database yet — with its images
     (uploaded files in scenarios/<id>/images/ and pictures from frontend/public/) stored in the database.
  2. Stories saved by the old `stories` table → story_runs + story_events (once).

Manual run:  uv run python -m src.import_data
"""
import asyncio
import json
from pathlib import Path
from typing import Dict, Optional

from sqlalchemy import select, text

from . import db
from . import scenario_store as store
from . import scenarios as scn
from .models import StoryEvent, StoryRun

PUBLIC_DIR = scn.PROJECT_ROOT / "frontend" / "public"
IMPORT_LOCK_ID = 728_391_005


def _local_image_file(url: str) -> Optional[Path]:
    """Map an image URL used in a scenario file to a file on disk, if there is one."""
    if not url or url.startswith(("http://", "https://", "data:", store.IMAGE_URL_PREFIX)):
        return None
    if url.startswith("/api/scenarios/"):
        parts = url.split("/")  # ['', 'api', 'scenarios', '<id>', 'images', '<file>']
        if len(parts) == 6 and parts[4] == "images":
            path = scn.SCENARIOS_DIR / parts[3] / "images" / parts[5]
            return path if path.is_file() else None
        return None
    path = PUBLIC_DIR / url.lstrip("/")
    return path if path.is_file() and path.resolve().parent == PUBLIC_DIR.resolve() else None


async def _store_image(url: str, scenario_id: str, cache: Dict[str, str]) -> str:
    if url in cache:
        return cache[url]
    path = _local_image_file(url)
    if path is None or not store.content_type_for(path.name):
        return url
    cache[url] = await store.save_image(scenario_id, path.name, path.read_bytes())
    return cache[url]


async def import_scenarios() -> list:
    """Import scenario files that aren't in the database yet. Existing database scenarios are never overwritten."""
    in_db = {s["id"] for s in await store.list_scenarios(include_drafts=True)}
    imported, cache = [], {}
    for path in sorted(scn.SCENARIOS_DIR.glob("*/scenario.json")):
        scenario_id = path.parent.name
        if scenario_id in in_db:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["background_image"] = await _store_image(data.get("background_image") or "", scenario_id, cache)
            for char in data.get("characters", []):
                char["image"] = await _store_image(char.get("image") or "", scenario_id, cache)
            await store.save_scenario(scenario_id, data, note="Imported from scenario.json", create=True, mirror=False)
            imported.append(scenario_id)
        except store.ScenarioExistsError:
            continue
        except Exception as e:
            print(f"[Import] Skipped '{scenario_id}': {e}")
    return imported


async def import_legacy_stories() -> int:
    """Copy rows from the old `stories` table into story_runs + story_events, once."""
    async with db.session() as s:
        has_table = (await s.execute(text("SELECT to_regclass('public.stories') IS NOT NULL"))).scalar()
        if not has_table:
            return 0
        already = (await s.execute(select(StoryRun.id).where(StoryRun.source == "imported").limit(1))).first()
        if already:
            return 0
        rows = (await s.execute(text(
            "SELECT id, scenario_id, language, title, scenario_text, turns, conclusion, turn_count, "
            "times_served, created_at, last_served_at FROM stories ORDER BY id"))).mappings().all()
    count = 0
    for row in rows:
        turns = row["turns"] or []
        async with db.session() as s, s.begin():
            run = StoryRun(scenario_id=row["scenario_id"], title=row["title"] or "", seed=row["scenario_text"] or "",
                           language=row["language"], status="completed", started_at=row["created_at"],
                           finished_at=row["created_at"], turn_count=row["turn_count"] or len(turns),
                           action_count=sum(1 for t in turns if t.get("actionText")),
                           conclusion=row["conclusion"] or "", turns=turns, in_replay_pool=True,
                           times_served=row["times_served"] or 0, last_served_at=row["last_served_at"],
                           source="imported", error=None)
            s.add(run)
            await s.flush()
            seq = 0
            for t in turns:
                pieces = [("director_narration", None, t.get("narration")), ("dialogue", t.get("speaker"), t.get("dialogue")),
                          ("action", t.get("speaker"), t.get("actionText"))]
                for kind, speaker, content in pieces:
                    if content:
                        seq += 1
                        s.add(StoryEvent(run_id=run.id, seq=seq, turn=t.get("turn"), type=kind, speaker=speaker,
                                         character_key=t.get("character") if speaker else None, content=content,
                                         data={"imported_from_story": row["id"]}))
            if row["conclusion"]:
                seq += 1
                s.add(StoryEvent(run_id=run.id, seq=seq, turn=turns[-1].get("turn") if turns else None,
                                 type="conclusion", content=row["conclusion"], data={"imported_from_story": row["id"]}))
        count += 1
    return count


async def run_imports() -> Dict:
    """Both imports under an advisory lock (two servers starting together won't double-import)."""
    if not db.enabled():
        return {}
    async with db.session() as s:
        conn = await s.connection()
        await conn.execute(text(f"SELECT pg_advisory_lock({IMPORT_LOCK_ID})"))
        try:
            scenarios = await import_scenarios()
            stories = await import_legacy_stories()
        finally:
            await conn.execute(text(f"SELECT pg_advisory_unlock({IMPORT_LOCK_ID})"))
            await s.commit()
    if scenarios or stories:
        print(f"[Import] Scenarios imported: {scenarios or 'none'}; old stories migrated: {stories}")
    return {"scenarios": scenarios, "stories": stories}


async def _main() -> None:
    await db.init_db()
    if not db.enabled():
        raise SystemExit("Database not connected — set DATABASE_URL in .env")
    print(await run_imports())
    await db.close_db()


if __name__ == "__main__":
    asyncio.run(_main())
