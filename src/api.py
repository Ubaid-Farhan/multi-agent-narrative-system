"""
FastAPI server for the narrative system.
POST /api/run: run full narrative once, store result, return frontend-shaped payload.
GET /api/story: return last stored story (for refresh / load without re-run).
"""
import asyncio
import base64
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import shutil
import sys
import time
from pathlib import Path

current_dir = Path(__file__).parent
project_root = current_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import edge_tts
from fastapi import Body, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from src.schemas import StoryState

from src.config import StoryConfig
from src.agents.character_agent import CharacterAgent
from src.agents.director_agent import DirectorAgent
from src.agents.reviewer_agent import ReviewerAgent
from src.graph.narrative_graph import NarrativeGraph
from src.story_state import StoryStateManager
from src import scenarios as scn
from src import db
from src.agents.base_agent import BaseAgent
from contextlib import asynccontextmanager

# In-memory store for the last run (frontend-shaped payload)
last_story: dict | None = None

DEFAULT_VOICE_PROFILE = {"voice": "hi-IN-MadhurNeural", "rate": "+0%", "pitch": "+0Hz"}


def _load_scenario_or_404(scenario_id: str) -> dict:
    try:
        return scn.load_scenario(scenario_id)
    except scn.ScenarioError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


def events_to_frontend_turns(events: list, seed_story: dict, conclusion_reason: str | None,
                             speaker_keys: dict | None = None) -> dict:
    """
    Transform backend events + seed_story + conclusion into frontend payload.
    Returns { title, scenario, turns, conclusion }.
    """
    title = seed_story.get("title", "")
    scenario = seed_story.get("description", "")
    conclusion = conclusion_reason or ""

    turns = []
    i = 0
    while i < len(events):
        e = events[i]
        if e.get("type") == "dialogue":
            # Collect all narrations since last dialogue (or start)
            narrations = []
            j = i - 1
            while j >= 0 and events[j].get("type") == "narration":
                narrations.append(events[j].get("content", ""))
                j -= 1
            narrations.reverse()
            narration = " ".join(narrations).strip() if narrations else ""

            speaker = e.get("speaker", "Unknown")
            character = (speaker_keys or {}).get(speaker, speaker.lower().replace(" ", "_")[:10])
            dialogue = e.get("content", "")

            # If next event is action with same turn, attach as actionText
            action_text = ""
            if i + 1 < len(events) and events[i + 1].get("type") == "action" and events[i + 1].get("turn") == e.get("turn"):
                action_text = events[i + 1].get("content", "")

            turn_obj = {
                "turn": len(turns) + 1,
                "speaker": speaker,
                "character": character,
                "narration": narration,
                "dialogue": dialogue,
            }
            if action_text:
                turn_obj["actionText"] = action_text
            turns.append(turn_obj)
            i += 1
            if action_text:
                i += 1
            continue
        i += 1

    return {
        "title": title,
        "scenario": scenario,
        "turns": turns,
        "conclusion": conclusion,
    }


def _build_story(scenario_id: str, language: str):
    """Build agents + graph for a scenario. Returns (scenario, seed_story, story_graph, story_manager, agents)."""
    scenario = _load_scenario_or_404(scenario_id)
    seed_story = {k: scenario.get(k) for k in ("title", "description", "setting")}
    config = StoryConfig.from_scenario(scenario, language=language)
    characters = [CharacterAgent(name=char["name"], config=config) for char in scenario["characters"]]
    director = DirectorAgent(config)
    reviewer = ReviewerAgent(config)
    story_manager = StoryStateManager(seed_story, scenario["characters"], config)
    story_graph = NarrativeGraph(config, characters, director, reviewer)
    return scenario, seed_story, story_graph, story_manager, (director, reviewer, characters)


def _speaker_keys(scenario: dict) -> dict:
    return {c["name"]: c["key"] for c in scenario.get("characters", [])}


async def run_narrative(scenario_id: str, language: str = "urdu"):
    """Run the full narrative. Returns (final_state, scenario, seed_story, director, reviewer, characters)."""
    scenario, seed_story, story_graph, story_manager, (director, reviewer, characters) = \
        _build_story(scenario_id, language)
    final_state = await story_graph.run(
        seed_story=seed_story,
        character_profiles=story_manager.state.character_profiles,
        character_memories=story_manager.state.character_memories,
    )
    return final_state, scenario, seed_story, director, reviewer, characters


def _build_graph_and_state(scenario_id: str, language: str = "urdu"):
    """Build narrative graph and initial state (for streaming). Returns (scenario, seed_story, story_graph, initial_state)."""
    scenario, seed_story, story_graph, story_manager, _ = _build_story(scenario_id, language)
    initial_state = StoryState(
        seed_story=seed_story,
        character_profiles=story_manager.state.character_profiles,
        character_memories=story_manager.state.character_memories,
        world_state=story_manager.state.world_state,
    )
    return scenario, seed_story, story_graph, initial_state


async def run_narrative_stream(scenario: dict, seed_story: dict, story_graph: NarrativeGraph,
                               initial_state: StoryState, language: str = "urdu"):
    """
    Stream graph steps; after each character_respond we have new events.
    Yields SSE payloads: meta, newTurns (per turn), conclusion, done.
    """
    global last_story
    title = seed_story.get("title", "")
    description = seed_story.get("description", "")
    speaker_keys = _speaker_keys(scenario)
    yield f"data: {json.dumps({'type': 'meta', 'title': title, 'scenario': description, 'scenarioId': scenario['id'], 'source': 'live'})}\n\n"
    try:
        stream = story_graph.graph.astream(initial_state, stream_mode="updates")
    except TypeError:
        stream = story_graph.graph.astream(initial_state)
    turns_sent = 0
    all_turns = []
    conclusion_reason = ""
    async for chunk in stream:
        if not isinstance(chunk, dict):
            continue
        for node_name, state_update in chunk.items():
            if node_name == "character_respond":
                events = state_update.get("events", []) if isinstance(state_update, dict) else getattr(state_update, "events", [])
                if not events:
                    continue
                payload = events_to_frontend_turns(events, seed_story, None, speaker_keys)
                new_turns = payload["turns"][turns_sent:]
                if new_turns:
                    turns_sent = len(payload["turns"])
                    all_turns.extend(new_turns)
                    yield f"data: {json.dumps({'type': 'turns', 'newTurns': new_turns})}\n\n"
            elif node_name == "check_conclusion":
                if (state_update.get("is_concluded") if isinstance(state_update, dict) else getattr(state_update, "is_concluded", False)):
                    conclusion_reason = state_update.get("conclusion_reason", "") if isinstance(state_update, dict) else getattr(state_update, "conclusion_reason", "") or ""
                    yield f"data: {json.dumps({'type': 'conclusion', 'conclusion': conclusion_reason})}\n\n"
            elif node_name == "conclude":
                pass  # conclusion_reason already sent from check_conclusion
    last_story = {"title": title, "scenario": description, "scenarioId": scenario["id"],
                  "turns": all_turns, "conclusion": conclusion_reason}
    await db.save_story(scenario["id"], language, last_story)
    yield f"data: {json.dumps({'type': 'done'})}\n\n"


# ─────────────────────────────── LLM availability + replay ───────────────────────────────

LLM_CHECK_TTL = 120          # seconds to trust a successful check
LLM_CHECK_TIMEOUT = 30       # seconds before a check counts as failed
REPLAY_TURN_DELAY = float(os.getenv("REPLAY_TURN_DELAY", "2.5"))  # pacing so a replay feels live
_llm_ok_until = 0.0


async def llm_available(scenario: dict, language: str) -> bool:
    """One tiny call through the same model + fallback chain the story uses."""
    global _llm_ok_until
    if time.time() < _llm_ok_until:
        return True
    if not (os.getenv("GOOGLE_API_KEY") or os.getenv("OPENAI_API_KEY")):
        print("[LLM] No API key configured.")
        return False
    try:
        llm = BaseAgent._build_llm(StoryConfig.from_scenario(scenario, language=language))
        response = await asyncio.wait_for(llm.ainvoke([("human", "Reply with the word OK.")]), LLM_CHECK_TIMEOUT)
        if not (response.text if isinstance(response.content, list) else response.content).strip():
            raise ValueError("empty response")
    except Exception as e:
        print(f"[LLM] Unavailable ({str(e)[:120]}) — will replay a saved story.")
        return False
    _llm_ok_until = time.time() + LLM_CHECK_TTL
    return True


async def replay_story_stream(scenario: dict, saved: dict):
    """Stream a saved story exactly as it was generated, turn by turn."""
    global last_story
    yield f"data: {json.dumps({'type': 'meta', 'title': saved['title'], 'scenario': saved['scenario'], 'scenarioId': scenario['id'], 'source': 'saved', 'storyId': saved['id']})}\n\n"
    for turn in saved["turns"]:
        await asyncio.sleep(REPLAY_TURN_DELAY)
        yield f"data: {json.dumps({'type': 'turns', 'newTurns': [turn]})}\n\n"
    if saved.get("conclusion"):
        yield f"data: {json.dumps({'type': 'conclusion', 'conclusion': saved['conclusion']})}\n\n"
    last_story = {"title": saved["title"], "scenario": saved["scenario"], "scenarioId": scenario["id"],
                  "turns": saved["turns"], "conclusion": saved.get("conclusion", "")}
    yield f"data: {json.dumps({'type': 'done'})}\n\n"


async def error_stream(message: str):
    yield f"data: {json.dumps({'type': 'error', 'message': message})}\n\n"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await db.init_db()
    yield
    await db.close_db()


app = FastAPI(title="AI Narrative Engine API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/tts")
async def api_tts(text: str, speaker: str = "", scenario: str = scn.DEFAULT_SCENARIO_ID):
    """Generate TTS with the character's voice profile (pitch + rate) from the scenario."""
    try:
        char = scn.get_character(scn.load_scenario(scenario), speaker)
    except (scn.ScenarioError, FileNotFoundError):
        char = {}
    profile = {**DEFAULT_VOICE_PROFILE, **(char.get("voice") or {})}
    try:
        communicate = edge_tts.Communicate(
            text=text,
            voice=profile["voice"],
            rate=profile["rate"],
            pitch=profile["pitch"],
        )
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        audio_bytes = buf.getvalue()
        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={
                "Content-Length": str(len(audio_bytes)),
                "Accept-Ranges": "bytes",
                "Cache-Control": "no-cache",
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/story")
def get_story():
    """Return the last run's story (frontend shape). Empty payload when none (200, no 404)."""
    if last_story is None:
        return {"title": None, "scenario": None, "turns": [], "conclusion": None}
    return last_story


@app.post("/api/run")
async def api_run(lang: str = "urdu", scenario: str = scn.DEFAULT_SCENARIO_ID):
    """Run the full narrative once, store result, return frontend-shaped payload."""
    global last_story
    try:
        final_state, scenario_data, seed_story, director, reviewer, characters = \
            await run_narrative(scenario, language=lang)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    events = final_state.get("events", [])
    conclusion_reason = final_state.get("conclusion_reason")
    payload = events_to_frontend_turns(events, seed_story, conclusion_reason, _speaker_keys(scenario_data))
    payload["scenarioId"] = scenario_data["id"]
    last_story = payload
    await db.save_story(scenario_data["id"], lang, payload)

    # Optionally write files (same as main.py) for consistency
    output_path = project_root / "story_output.json"
    action_count = sum(1 for e in events if e.get("type") == "action")
    output_data = {
        "title": seed_story.get("title"),
        "seed_story": seed_story,
        "events": events,
        "conclusion": conclusion_reason,
        "metadata": {
            "total_turns": final_state["current_turn"],
            "total_actions": action_count,
            "conclusion_reason": conclusion_reason,
        },
    }
    output_path.write_text(json.dumps(output_data, indent=2, default=str))

    all_logs = []
    for log in director.logs:
        log["role"] = "Director"
        all_logs.append(log)
    for log in reviewer.logs:
        log["role"] = "Reviewer"
        all_logs.append(log)
    for char in characters:
        for log in char.logs:
            log["role"] = f"Character ({char.name})"
            all_logs.append(log)
    all_logs.sort(key=lambda x: x["timestamp"])
    prompts_path = project_root / "prompts_log.json"
    prompts_path.write_text(json.dumps(all_logs, indent=2, default=str))

    return payload


@app.get("/api/run/stream")
async def api_run_stream(lang: str = "urdu", scenario: str = scn.DEFAULT_SCENARIO_ID, mode: str = "auto"):
    """
    Stream a story as SSE. Events: meta (title, scenario, source), turns (newTurns), conclusion, done, error.
    mode=auto: generate live if the LLM responds, otherwise replay a saved story.
    mode=live: always generate. mode=saved: always replay a saved story.
    """
    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    if mode not in ("auto", "live", "saved"):
        raise HTTPException(status_code=422, detail="mode must be auto, live or saved")
    scenario_data = _load_scenario_or_404(scenario)

    if mode == "saved" or (mode == "auto" and not await llm_available(scenario_data, lang)):
        saved = await db.pick_story(scenario_data["id"], lang)
        if saved:
            print(f"[Replay] Serving saved story #{saved['id']} ({saved['language']})")
            return StreamingResponse(replay_story_stream(scenario_data, saved),
                                     media_type="text/event-stream", headers=headers)
        message = ("The AI is unavailable right now (API key failed or quota exhausted) and there is no "
                   "saved story for this scenario yet. Please try again later.")
        return StreamingResponse(error_stream(message), media_type="text/event-stream", headers=headers)

    try:
        scenario_data, seed_story, story_graph, initial_state = _build_graph_and_state(scenario, language=lang)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return StreamingResponse(
        run_narrative_stream(scenario_data, seed_story, story_graph, initial_state, lang),
        media_type="text/event-stream",
        headers=headers,
    )


# ─────────────────────────────── Scenarios (public) ───────────────────────────────

@app.get("/api/scenarios")
def api_list_scenarios():
    """List available scenarios for the story player."""
    return {"scenarios": scn.list_scenarios(), "default": scn.DEFAULT_SCENARIO_ID}


@app.get("/api/scenarios/{scenario_id}")
def api_get_scenario_public(scenario_id: str):
    """Scenario info for the story player (characters, images, colors) — no prompts."""
    return scn.public_view(_load_scenario_or_404(scenario_id))


@app.get("/api/scenarios/{scenario_id}/images/{filename}")
def api_scenario_image(scenario_id: str, filename: str):
    """Serve an image uploaded from the admin panel."""
    try:
        images_dir = (scn.scenario_dir(scenario_id) / "images").resolve()
    except scn.ScenarioError as e:
        raise HTTPException(status_code=400, detail=str(e))
    path = (images_dir / filename).resolve()
    if path.parent != images_dir or not path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path)


# ─────────────────────────────── Admin (password protected) ───────────────────────────────

ADMIN_TOKEN_TTL = 12 * 60 * 60  # seconds
ALLOWED_IMAGE_TYPES = {".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg", ".webp": "webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
TTS_VOICES = [
    "hi-IN-MadhurNeural", "hi-IN-SwaraNeural", "ur-PK-AsadNeural", "ur-PK-UzmaNeural",
    "ur-IN-SalmanNeural", "ur-IN-GulNeural", "en-IN-PrabhatNeural", "en-IN-NeerjaNeural",
    "en-US-GuyNeural", "en-US-JennyNeural",
]
CHARACTER_COLORS = ["amber", "blue", "slate", "emerald", "rose", "violet", "cyan", "orange"]


def _admin_key() -> bytes:
    password = os.getenv("ADMIN_PASSWORD", "")
    if not password:
        raise HTTPException(status_code=503, detail="Admin panel disabled: set ADMIN_PASSWORD in .env and restart the API.")
    return hashlib.sha256(("admin-token:" + password).encode()).digest()


def _sign(expiry: int) -> str:
    return hmac.new(_admin_key(), str(expiry).encode(), hashlib.sha256).hexdigest()


def require_admin(authorization: str = Header(default="")) -> None:
    """Checks 'Authorization: Bearer <expiry>.<signature>'. Changing ADMIN_PASSWORD revokes all tokens."""
    token = authorization.removeprefix("Bearer ").strip()
    expiry_text, _, signature = token.partition(".")
    if not expiry_text.isdigit() or not hmac.compare_digest(signature, _sign(int(expiry_text))):
        raise HTTPException(status_code=401, detail="Not logged in")
    if int(expiry_text) < time.time():
        raise HTTPException(status_code=401, detail="Session expired, please log in again")


@app.post("/api/admin/login")
def api_admin_login(payload: dict = Body(...)):
    expected = os.getenv("ADMIN_PASSWORD", "")
    _admin_key()  # 503 if not configured
    if not hmac.compare_digest(str(payload.get("password", "")).encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Wrong password")
    expiry = int(time.time()) + ADMIN_TOKEN_TTL
    return {"token": f"{expiry}.{_sign(expiry)}", "expires": expiry}


@app.get("/api/admin/meta", dependencies=[Depends(require_admin)])
def api_admin_meta():
    """Editor helpers: placeholders per prompt, TTS voices, colors, default settings."""
    return {
        "prompts": scn.PROMPT_PLACEHOLDERS,
        "voices": TTS_VOICES,
        "colors": CHARACTER_COLORS,
        "default_settings": scn.DEFAULT_SETTINGS,
    }


@app.get("/api/admin/scenarios/{scenario_id}", dependencies=[Depends(require_admin)])
def api_admin_get_scenario(scenario_id: str):
    return _load_scenario_or_404(scenario_id)


@app.put("/api/admin/scenarios/{scenario_id}", dependencies=[Depends(require_admin)])
def api_admin_save_scenario(scenario_id: str, payload: dict = Body(...)):
    _load_scenario_or_404(scenario_id)
    try:
        return scn.save_scenario(scenario_id, payload)
    except scn.ScenarioError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.post("/api/admin/scenarios", dependencies=[Depends(require_admin)])
def api_admin_create_scenario(payload: dict = Body(...)):
    """Create a scenario by copying an existing one (default: the built-in scenario)."""
    new_id = str(payload.get("id", "")).strip()
    source_id = payload.get("copy_from") or scn.DEFAULT_SCENARIO_ID
    try:
        target = scn.scenario_dir(new_id)
    except scn.ScenarioError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if target.exists():
        raise HTTPException(status_code=409, detail=f"Scenario '{new_id}' already exists")
    data = _load_scenario_or_404(source_id)
    data["title"] = str(payload.get("title") or f"{data.get('title', '')} (copy)").strip()
    saved = scn.save_scenario(new_id, data)
    source_images = scn.scenario_dir(source_id) / "images"
    if source_images.is_dir():
        shutil.copytree(source_images, target / "images")
        prefix_old = f"/api/scenarios/{source_id}/images/"
        prefix_new = f"/api/scenarios/{new_id}/images/"
        for char in saved["characters"]:
            if char.get("image", "").startswith(prefix_old):
                char["image"] = prefix_new + char["image"][len(prefix_old):]
        if saved.get("background_image", "").startswith(prefix_old):
            saved["background_image"] = prefix_new + saved["background_image"][len(prefix_old):]
        saved = scn.save_scenario(new_id, saved)
    return saved


@app.delete("/api/admin/scenarios/{scenario_id}", dependencies=[Depends(require_admin)])
def api_admin_delete_scenario(scenario_id: str):
    if scenario_id == scn.DEFAULT_SCENARIO_ID:
        raise HTTPException(status_code=400, detail="The default scenario cannot be deleted.")
    _load_scenario_or_404(scenario_id)
    shutil.rmtree(scn.scenario_dir(scenario_id))
    return {"deleted": scenario_id}


@app.post("/api/admin/scenarios/{scenario_id}/images", dependencies=[Depends(require_admin)])
def api_admin_upload_image(scenario_id: str, payload: dict = Body(...)):
    """Upload an image as base64 ({filename, data}). Returns the URL to store in the scenario."""
    _load_scenario_or_404(scenario_id)
    filename = str(payload.get("filename", ""))
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=422, detail="Only PNG, JPG or WEBP images are allowed.")
    data = str(payload.get("data", ""))
    if "," in data and data.startswith("data:"):
        data = data.split(",", 1)[1]
    try:
        raw = base64.b64decode(data, validate=True)
    except ValueError:
        raise HTTPException(status_code=422, detail="Image data is not valid base64.")
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image is larger than 5 MB.")
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", Path(filename).stem).strip("-")[:40] or "image"
    name = f"{stem}-{secrets.token_hex(4)}{ext}"
    images_dir = scn.scenario_dir(scenario_id) / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    (images_dir / name).write_bytes(raw)
    return {"url": f"/api/scenarios/{scenario_id}/images/{name}"}
