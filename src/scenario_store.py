"""
Scenario storage. The database is the source of truth for everything the admin panel edits:
scenarios, characters, prompts, images and a version snapshot on every save.

- Every save is mirrored to scenarios/<id>/scenario.json (backup, git history, offline fallback).
- If the database is unavailable, scenarios are read from those JSON files (read-only) so the player
  keeps working; any write raises ReadOnlyError.
"""
import base64
import copy
import hashlib
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sqlalchemy import delete, select

from . import db
from . import scenarios as scn
from .models import Character, Image, Prompt, Scenario, ScenarioVersion

IMAGE_URL_PREFIX = "/api/images/"
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
EXPORT_FORMAT = "narrative-scenario/v1"

TOP_FIELDS = ("title", "subtitle", "description", "setting", "background_image", "status", "settings", "generated_from")
CHARACTER_FIELDS = ("key", "name", "label", "description", "goals", "inventory", "persona", "english_style",
                    "appeals", "review_notes_urdu", "review_notes_english", "voice", "image", "color")
META_KEYS = {"id", "characters", "prompts", "version", "updated_at", "created_at"}

CACHE_TTL = 30  # seconds; scenarios are read on every story start and every TTS line
_cache: Dict[str, Tuple[float, Dict]] = {}


class ReadOnlyError(RuntimeError):
    """The database is not connected, so admin changes can't be saved."""

    def __init__(self):
        super().__init__("The database is not connected — admin changes are disabled (read-only mode). "
                         "Check DATABASE_URL and restart the API.")


class ScenarioExistsError(ValueError):
    pass


def _invalidate(scenario_id: Optional[str] = None) -> None:
    if scenario_id is None:
        _cache.clear()
    else:
        _cache.pop(scenario_id, None)


async def _require_db() -> None:
    if not await db.ensure():
        raise ReadOnlyError()


def writable() -> bool:
    return db.enabled()


# ─────────────────────────────── row <-> dict ───────────────────────────────

def _to_dict(sc: Scenario, chars: List[Character], prompts: List[Prompt]) -> Dict:
    data: Dict = {"id": sc.id}
    data.update(sc.extra or {})
    for field in TOP_FIELDS:
        value = getattr(sc, field)
        if field == "generated_from" and value is None:
            continue
        data[field] = copy.deepcopy(value)
    data["settings"] = {**scn.DEFAULT_SETTINGS, **(data.get("settings") or {})}
    data["characters"] = [{f: copy.deepcopy(getattr(c, f)) for f in CHARACTER_FIELDS}
                          for c in sorted(chars, key=lambda c: c.position)]
    data["prompts"] = {p.name: p.template for p in prompts}
    data["version"] = sc.version
    data["updated_at"] = sc.updated_at.isoformat() if sc.updated_at else None
    return data


def _plain(data: Dict) -> Dict:
    """Scenario data without database metadata (for snapshots, files and exports)."""
    return {k: v for k, v in data.items() if k not in ("version", "updated_at", "created_at")}


async def _load_from_db(session, scenario_id: str) -> Optional[Dict]:
    sc = await session.get(Scenario, scenario_id)
    if sc is None:
        return None
    chars = (await session.execute(select(Character).where(Character.scenario_id == scenario_id))).scalars().all()
    prompts = (await session.execute(select(Prompt).where(Prompt.scenario_id == scenario_id))).scalars().all()
    return _to_dict(sc, list(chars), list(prompts))


# ─────────────────────────────── read ───────────────────────────────

async def list_scenarios(include_drafts: bool = False) -> List[Dict]:
    if not await db.ensure():
        return scn.list_scenarios(include_drafts=include_drafts)
    async with db.session() as s:
        rows = (await s.execute(select(Scenario.id, Scenario.title, Scenario.status, Scenario.version,
                                       Scenario.updated_at).order_by(Scenario.title))).all()
    return [{"id": r.id, "title": r.title, "status": r.status, "version": r.version,
             "updated_at": r.updated_at.isoformat() if r.updated_at else None}
            for r in rows if include_drafts or r.status != "draft"]


async def load_scenario(scenario_id: str = scn.DEFAULT_SCENARIO_ID) -> Dict:
    """Raises scn.ScenarioError for a bad id and FileNotFoundError if it doesn't exist."""
    scn._check_id(scenario_id)
    if not await db.ensure():
        return scn.load_scenario(scenario_id)
    cached = _cache.get(scenario_id)
    if cached and time.time() - cached[0] < CACHE_TTL:
        return copy.deepcopy(cached[1])
    async with db.session() as s:
        data = await _load_from_db(s, scenario_id)
    if data is None:
        raise FileNotFoundError(f"Scenario '{scenario_id}' not found")
    _cache[scenario_id] = (time.time(), data)
    return copy.deepcopy(data)


async def exists(scenario_id: str) -> bool:
    try:
        await load_scenario(scenario_id)
        return True
    except FileNotFoundError:
        return False


async def unique_id(title: str) -> str:
    """Slug from a title that doesn't collide with an existing scenario (database or folder)."""
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:56] or "scenario"
    if not slug[0].isalnum():
        slug = "s" + slug
    taken = {s["id"] for s in await list_scenarios(include_drafts=True)}
    taken |= {p.name for p in scn.SCENARIOS_DIR.glob("*") if p.is_dir()}
    candidate, n = slug, 2
    while candidate in taken:
        candidate, n = f"{slug}_{n}", n + 1
    return candidate


# ─────────────────────────────── write ───────────────────────────────

_LIST_FIELDS = {"goals", "inventory"}
_DICT_FIELDS = {"appeals", "voice"}


def _character_columns(char: Dict) -> Dict:
    """Character dict → column values, with empty defaults instead of null."""
    values = {}
    for field in CHARACTER_FIELDS:
        value = char.get(field)
        if value is None:
            value = [] if field in _LIST_FIELDS else {} if field in _DICT_FIELDS else ""
        values[field] = value
    values["color"] = values["color"] or "slate"
    return values


def _mirror_to_file(scenario_id: str, data: Dict) -> None:
    try:
        scn.save_scenario(scenario_id, _plain(data))
    except Exception as e:  # the database already has it; the file is only a mirror
        print(f"[Store] Could not mirror '{scenario_id}' to its JSON file: {e}")


async def save_scenario(scenario_id: str, data: Dict, note: str = "Saved from admin panel",
                        create: bool = False, mirror: bool = True) -> Dict:
    """Validate and save (insert or update). Every save bumps `version` and stores a snapshot."""
    await _require_db()
    scn._check_id(scenario_id)
    clean = scn.validate_scenario(_plain(data))
    clean["id"] = scenario_id

    async with db.session() as s, s.begin():
        sc = await s.get(Scenario, scenario_id, with_for_update=True)
        if create and sc is not None:
            raise ScenarioExistsError(f"Scenario '{scenario_id}' already exists")
        if not create and sc is None:
            raise FileNotFoundError(f"Scenario '{scenario_id}' not found")
        if sc is None:
            sc = Scenario(id=scenario_id, version=0)
            s.add(sc)

        for field in TOP_FIELDS:
            default = None if field == "generated_from" else ({} if field in ("setting", "settings") else "")
            setattr(sc, field, clean.get(field, default))
        sc.extra = {k: v for k, v in clean.items() if k not in META_KEYS and k not in TOP_FIELDS}
        sc.version = (sc.version or 0) + 1
        await s.flush()

        await s.execute(delete(Character).where(Character.scenario_id == scenario_id))
        await s.execute(delete(Prompt).where(Prompt.scenario_id == scenario_id))
        for position, char in enumerate(clean["characters"]):
            s.add(Character(scenario_id=scenario_id, position=position, **_character_columns(char)))
        for name, template in clean["prompts"].items():
            s.add(Prompt(scenario_id=scenario_id, name=name, template=template))
        s.add(ScenarioVersion(scenario_id=scenario_id, version=sc.version, snapshot=_plain(clean), note=note))

    _invalidate(scenario_id)
    saved = await load_scenario(scenario_id)
    if mirror:
        _mirror_to_file(scenario_id, saved)
    return saved


async def create_copy(new_id: str, source_id: str, title: Optional[str] = None) -> Dict:
    data = await load_scenario(source_id)
    data["title"] = str(title or f"{data.get('title', '')} (copy)").strip()
    return await save_scenario(new_id, data, note=f"Copied from '{source_id}'", create=True)


def _image_ids_in(data: Dict) -> set:
    urls = [data.get("background_image") or ""] + [c.get("image") or "" for c in data.get("characters", [])]
    return {u[len(IMAGE_URL_PREFIX):] for u in urls if u.startswith(IMAGE_URL_PREFIX)}


async def _referenced_image_ids(session) -> set:
    ids = set()
    for (bg,) in (await session.execute(select(Scenario.background_image))).all():
        if bg and bg.startswith(IMAGE_URL_PREFIX):
            ids.add(bg[len(IMAGE_URL_PREFIX):])
    for (img,) in (await session.execute(select(Character.image))).all():
        if img and img.startswith(IMAGE_URL_PREFIX):
            ids.add(img[len(IMAGE_URL_PREFIX):])
    return ids


async def delete_scenario(scenario_id: str) -> None:
    """Delete a scenario, its history, and images no other scenario uses. Story runs are kept."""
    await _require_db()
    data = await load_scenario(scenario_id)
    async with db.session() as s, s.begin():
        await s.execute(delete(Scenario).where(Scenario.id == scenario_id))
        still_used = await _referenced_image_ids(s)
        orphaned = [uuid.UUID(i) for i in _image_ids_in(data) - still_used if _is_uuid(i)]
        if orphaned:
            await s.execute(delete(Image).where(Image.id.in_(orphaned)))
    _invalidate(scenario_id)
    folder = scn.SCENARIOS_DIR / scenario_id
    if folder.is_dir():
        shutil.rmtree(folder, ignore_errors=True)


# ─────────────────────────────── versions ───────────────────────────────

async def list_versions(scenario_id: str) -> List[Dict]:
    await _require_db()
    async with db.session() as s:
        rows = (await s.execute(select(ScenarioVersion.version, ScenarioVersion.note, ScenarioVersion.created_at)
                                .where(ScenarioVersion.scenario_id == scenario_id)
                                .order_by(ScenarioVersion.version.desc()))).all()
    return [{"version": r.version, "note": r.note, "created_at": r.created_at.isoformat()} for r in rows]


async def get_version(scenario_id: str, version: int) -> Dict:
    await _require_db()
    async with db.session() as s:
        row = (await s.execute(select(ScenarioVersion).where(ScenarioVersion.scenario_id == scenario_id,
                                                             ScenarioVersion.version == version))).scalar_one_or_none()
    if row is None:
        raise FileNotFoundError(f"Version {version} of '{scenario_id}' not found")
    return {**row.snapshot, "id": scenario_id}


async def restore_version(scenario_id: str, version: int) -> Dict:
    snapshot = await get_version(scenario_id, version)
    return await save_scenario(scenario_id, snapshot, note=f"Restored version {version}")


# ─────────────────────────────── images ───────────────────────────────

def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def content_type_for(filename: str) -> Optional[str]:
    return IMAGE_TYPES.get(Path(filename).suffix.lower())


async def save_image(scenario_id: Optional[str], filename: str, raw: bytes) -> str:
    """Store image bytes (deduplicated by content) and return its URL."""
    await _require_db()
    content_type = content_type_for(filename)
    if not content_type:
        raise ValueError("Only PNG, JPG or WEBP images are allowed.")
    digest = hashlib.sha256(raw).hexdigest()
    async with db.session() as s, s.begin():
        existing = (await s.execute(select(Image.id).where(Image.sha256 == digest))).scalar_one_or_none()
        if existing:
            return f"{IMAGE_URL_PREFIX}{existing}"
        image = Image(id=uuid.uuid4(), scenario_id=scenario_id, filename=Path(filename).name[:200],
                      content_type=content_type, size=len(raw), sha256=digest, data=raw)
        s.add(image)
    return f"{IMAGE_URL_PREFIX}{image.id}"


async def get_image(image_id: str) -> Optional[Tuple[bytes, str]]:
    if not _is_uuid(image_id) or not await db.ensure():
        return None
    async with db.session() as s:
        row = (await s.execute(select(Image.data, Image.content_type).where(Image.id == uuid.UUID(image_id)))).first()
    return (row.data, row.content_type) if row else None


# ─────────────────────────────── export / import ───────────────────────────────

async def export_scenario(scenario_id: str) -> Dict:
    """Portable JSON: the scenario plus every database image it uses, embedded as data URLs."""
    data = _plain(await load_scenario(scenario_id))
    images = {}
    for image_id in _image_ids_in(data):
        found = await get_image(image_id)
        if found:
            raw, content_type = found
            images[f"{IMAGE_URL_PREFIX}{image_id}"] = f"data:{content_type};base64,{base64.b64encode(raw).decode()}"
    return {"format": EXPORT_FORMAT, "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "scenario": data, "images": images}


def _ext_for(content_type: str) -> str:
    return next((ext for ext, ct in IMAGE_TYPES.items() if ct == content_type), ".png")


async def import_scenario(payload: Dict) -> Dict:
    """Import an export (or a plain scenario.json) as a new scenario with a free id."""
    await _require_db()
    data = copy.deepcopy(payload.get("scenario") if payload.get("format") == EXPORT_FORMAT else payload)
    if not isinstance(data, dict):
        raise scn.ScenarioError("Not a scenario file.")
    url_map = {}
    for old_url, data_url in (payload.get("images") or {}).items():
        match = re.match(r"^data:([\w/+.-]+);base64,(.*)$", str(data_url), flags=re.S)
        if not match:
            continue
        raw = base64.b64decode(match.group(2))
        url_map[old_url] = await save_image(None, f"imported{_ext_for(match.group(1))}", raw)
    if data.get("background_image") in url_map:
        data["background_image"] = url_map[data["background_image"]]
    for char in data.get("characters", []):
        if char.get("image") in url_map:
            char["image"] = url_map[char["image"]]
    new_id = await unique_id(str(data.get("title") or "imported"))
    return await save_scenario(new_id, data, note="Imported from file", create=True)
