"""
FastAPI server for the narrative system: story player (SSE), TTS, replay fallback, admin panel API.
Scenarios / characters / prompts / images live in the database (src/scenario_store.py) and every story
run is recorded step by step (src/run_recorder.py).
"""
import asyncio
import base64
import hashlib
import hmac
import io
import json
import os
import sys
import time
import warnings
from pathlib import Path

# A harmless bug inside the Gemini client's error handling prints this on every failed call.
warnings.filterwarnings("ignore", message="coroutine 'ClientResponse.json' was never awaited")

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
from src import scenario_generator
from src import image_generator
from src import scenario_store as store
from src import run_recorder
from src.run_recorder import RunRecorder
from src.import_data import run_imports
from src.agents.base_agent import BaseAgent, LLMUnavailableError
from contextlib import asynccontextmanager

# In-memory store for the last run (frontend-shaped payload)
last_story: dict | None = None

DEFAULT_VOICE_PROFILE = {"voice": "hi-IN-MadhurNeural", "rate": "+0%", "pitch": "+0Hz"}


def _http_error(e: Exception) -> HTTPException:
    """Map storage errors to HTTP responses."""
    if isinstance(e, HTTPException):
        return e
    if isinstance(e, store.ReadOnlyError):
        return HTTPException(status_code=503, detail=str(e))
    if isinstance(e, store.ScenarioExistsError):
        return HTTPException(status_code=409, detail=str(e))
    if isinstance(e, scn.ScenarioError):
        return HTTPException(status_code=422, detail=str(e))
    if isinstance(e, FileNotFoundError):
        return HTTPException(status_code=404, detail=str(e))
    return HTTPException(status_code=500, detail=str(e))


async def _load_scenario_or_404(scenario_id: str) -> dict:
    try:
        return await store.load_scenario(scenario_id)
    except Exception as e:
        raise _http_error(e)


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


def _build_story(scenario: dict, language: str, recorder: RunRecorder | None = None):
    """Build agents + graph for a scenario. Returns (scenario, seed_story, story_graph, story_manager, agents)."""
    seed_story = {k: scenario.get(k) for k in ("title", "description", "setting")}
    config = StoryConfig.from_scenario(scenario, language=language)
    config.recorder = recorder
    characters = [CharacterAgent(name=char["name"], config=config) for char in scenario["characters"]]
    director = DirectorAgent(config)
    reviewer = ReviewerAgent(config)
    story_manager = StoryStateManager(seed_story, scenario["characters"], config)
    story_graph = NarrativeGraph(config, characters, director, reviewer)
    return scenario, seed_story, story_graph, story_manager, (director, reviewer, characters)


def _speaker_keys(scenario: dict) -> dict:
    return {c["name"]: c["key"] for c in scenario.get("characters", [])}


async def run_narrative(scenario: dict, language: str = "urdu", recorder: RunRecorder | None = None):
    """Run the full narrative. Returns (final_state, scenario, seed_story, director, reviewer, characters)."""
    scenario, seed_story, story_graph, story_manager, (director, reviewer, characters) = \
        _build_story(scenario, language, recorder)
    final_state = await story_graph.run(
        seed_story=seed_story,
        character_profiles=story_manager.state.character_profiles,
        character_memories=story_manager.state.character_memories,
    )
    return final_state, scenario, seed_story, director, reviewer, characters


def _build_graph_and_state(scenario: dict, language: str = "urdu", recorder: RunRecorder | None = None):
    """Build narrative graph and initial state (for streaming). Returns (scenario, seed_story, story_graph, initial_state)."""
    scenario, seed_story, story_graph, story_manager, _ = _build_story(scenario, language, recorder)
    initial_state = StoryState(
        seed_story=seed_story,
        character_profiles=story_manager.state.character_profiles,
        character_memories=story_manager.state.character_memories,
        world_state=story_manager.state.world_state,
    )
    return scenario, seed_story, story_graph, initial_state


def _action_count(turns: list) -> int:
    return sum(1 for t in turns if t.get("actionText"))


def _state_dict(state) -> dict:
    """A graph state (pydantic model or dict) as plain JSON-able data."""
    if isinstance(state, StoryState):
        return state.model_dump(mode="json")
    return StoryState.model_validate(state).model_dump(mode="json")


async def run_narrative_stream(scenario: dict, seed_story: dict, story_graph: NarrativeGraph,
                               initial_state: StoryState, language: str = "urdu",
                               recorder: RunRecorder | None = None, previous_turns: list | None = None):
    """
    Stream the story; yields SSE payloads: meta, turns (newTurns), conclusion, done (or error).
    After every turn the run is checkpointed (turns + full state), so an unfinished run can be continued.
    `previous_turns`: turns already shown when continuing a run; they are sent first.
    """
    global last_story
    title = seed_story.get("title", "")
    description = seed_story.get("description", "")
    speaker_keys = _speaker_keys(scenario)
    run_id = recorder.run_id if recorder else None
    resumed = bool(previous_turns)
    yield f"data: {json.dumps({'type': 'meta', 'title': title, 'scenario': description, 'scenarioId': scenario['id'], 'source': 'live', 'runId': run_id, 'resumed': resumed})}\n\n"

    all_turns = list(previous_turns or [])
    if all_turns:
        yield f"data: {json.dumps({'type': 'turns', 'newTurns': all_turns})}\n\n"
    turns_sent = len(all_turns)
    conclusion_reason = ""
    status, error = "aborted", None
    try:
        async for state in story_graph.graph.astream(initial_state, stream_mode="values"):
            data = state.model_dump() if isinstance(state, StoryState) else state
            events = data.get("events") or []
            payload = events_to_frontend_turns(events, seed_story, None, speaker_keys)
            new_turns = payload["turns"][turns_sent:]
            if new_turns:
                turns_sent = len(payload["turns"])
                all_turns.extend(new_turns)
                if recorder:
                    recorder.checkpoint(all_turns, _state_dict(state), _action_count(all_turns))
                yield f"data: {json.dumps({'type': 'turns', 'newTurns': new_turns})}\n\n"
            if data.get("is_concluded") and not conclusion_reason:
                conclusion_reason = data.get("conclusion_reason") or ""
                yield f"data: {json.dumps({'type': 'conclusion', 'conclusion': conclusion_reason})}\n\n"
        status = "completed" if db.is_complete(all_turns, conclusion_reason) else "incomplete"
    except LLMUnavailableError as e:
        status, error = "failed", f"No AI model could answer ({e})"
        print(f"[Story] Stopped: {error}")
    except Exception as e:
        status, error = "failed", str(e) or e.__class__.__name__
        print(f"[Story] Run failed: {e!r}")
        if recorder:
            recorder.event("error", content="Story run failed", error=error)
    finally:
        last_story = {"title": title, "scenario": description, "scenarioId": scenario["id"],
                      "turns": all_turns, "conclusion": conclusion_reason}
        if recorder:
            try:
                await asyncio.shield(recorder.finish(status, turns=all_turns, conclusion=conclusion_reason,
                                                     error=error, turn_count=len(all_turns),
                                                     action_count=_action_count(all_turns)))
            except BaseException:
                pass  # viewer left mid-save; the shielded save still completes
    if status == "failed":
        saved_note = f" Run #{run_id} is saved — press Continue later to pick up from turn {len(all_turns)}." \
            if run_id and all_turns else ""
        if error and error.startswith("No AI model"):
            message = (f"The story stopped after {len(all_turns)} turn(s): the AI is unavailable right now "
                       "(daily quota used up or the service is busy)." + saved_note)
        else:
            message = "The story stopped because of an error: " + (error or "")[:300] + saved_note
        yield f"data: {json.dumps({'type': 'error', 'message': message, 'turns': len(all_turns), 'runId': run_id})}\n\n"
    yield f"data: {json.dumps({'type': 'done', 'runId': run_id})}\n\n"


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
        # Same model order and cooldowns as a real story: models known to be out of quota are skipped.
        probe = BaseAgent("Health check", StoryConfig.from_scenario(scenario, language=language))
        probe.max_wait = 0
        await asyncio.wait_for(probe.generate_response("Reply with the word OK."), LLM_CHECK_TIMEOUT)
    except Exception as e:
        print(f"[LLM] Unavailable ({str(e)[:120]}) — will replay a saved story.")
        return False
    _llm_ok_until = time.time() + LLM_CHECK_TTL
    return True


async def replay_story_stream(scenario: dict, saved: dict):
    """Stream a saved run exactly as it was generated, turn by turn."""
    global last_story
    yield f"data: {json.dumps({'type': 'meta', 'title': saved['title'], 'scenario': saved['scenario'], 'scenarioId': scenario['id'], 'source': 'saved', 'runId': saved['id']})}\n\n"
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


async def _startup_maintenance() -> None:
    """Import file scenarios / old stories, close runs cut off by a restart, prune old LLM logs."""
    try:
        await run_imports()
        stale = await run_recorder.close_stale_runs()
        pruned = await run_recorder.cleanup_llm_calls()
        if stale or pruned:
            print(f"[DB] Closed {stale} interrupted run(s); deleted {pruned} LLM log row(s) older than "
                  f"{run_recorder.LLM_LOG_RETENTION_DAYS} days.")
    except Exception as e:
        print(f"[DB] Startup maintenance failed: {e!r}")


async def _daily_cleanup() -> None:
    while True:
        await asyncio.sleep(24 * 60 * 60)
        try:
            await run_recorder.cleanup_llm_calls()
        except Exception as e:
            print(f"[DB] LLM log cleanup failed: {e!r}")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await db.init_db()
    cleanup_task = None
    if db.enabled():
        await _startup_maintenance()
        cleanup_task = asyncio.create_task(_daily_cleanup())
    yield
    if cleanup_task:
        cleanup_task.cancel()
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
        char = scn.get_character(await store.load_scenario(scenario), speaker)
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
    scenario_data = await _load_scenario_or_404(scenario)
    recorder = RunRecorder(scenario_data, lang, source="api")
    await recorder.start()
    try:
        final_state, scenario_data, seed_story, director, reviewer, characters = \
            await run_narrative(scenario_data, language=lang, recorder=recorder)
    except Exception as e:
        recorder.event("error", content="Story run failed", error=str(e))
        await recorder.finish("failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

    events = final_state.get("events", [])
    conclusion_reason = final_state.get("conclusion_reason")
    payload = events_to_frontend_turns(events, seed_story, conclusion_reason, _speaker_keys(scenario_data))
    payload["scenarioId"] = scenario_data["id"]
    payload["runId"] = recorder.run_id
    last_story = payload
    await recorder.finish("completed" if db.is_complete(payload["turns"], conclusion_reason or "") else "incomplete",
                          turns=payload["turns"], conclusion=conclusion_reason or "",
                          turn_count=len(payload["turns"]), action_count=_action_count(payload["turns"]))

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
    output_path.write_text(json.dumps(output_data, indent=2, default=str), encoding="utf-8")

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
    prompts_path.write_text(json.dumps(all_logs, indent=2, default=str), encoding="utf-8")

    return payload


@app.get("/api/run/stream")
async def api_run_stream(lang: str = "urdu", scenario: str = scn.DEFAULT_SCENARIO_ID, mode: str = "auto",
                         continue_run: int | None = None):
    """
    Stream a story as SSE. Events: meta (title, scenario, source), turns (newTurns), conclusion, done, error.
    mode=auto: generate live if the LLM responds, otherwise replay a saved story.
    mode=live: always generate. mode=saved: always replay a saved story.
    continue_run=<run id>: continue an unfinished run from its last saved turn (same run number).
    """
    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    if continue_run is not None:
        return await _continue_run_stream(continue_run, headers)
    if mode not in ("auto", "live", "saved"):
        raise HTTPException(status_code=422, detail="mode must be auto, live or saved")
    scenario_data = await _load_scenario_or_404(scenario)

    if mode == "saved" or (mode == "auto" and not await llm_available(scenario_data, lang)):
        saved = await run_recorder.pick_replay(scenario_data["id"], lang)
        if saved:
            print(f"[Replay] Serving saved run #{saved['id']} ({saved['language']})")
            return StreamingResponse(replay_story_stream(scenario_data, saved),
                                     media_type="text/event-stream", headers=headers)
        message = ("The AI is unavailable right now (API key failed or quota exhausted) and there is no "
                   "saved story for this scenario yet. Please try again later.")
        return StreamingResponse(error_stream(message), media_type="text/event-stream", headers=headers)

    recorder = RunRecorder(scenario_data, lang, source="api")
    await recorder.start()
    try:
        scenario_data, seed_story, story_graph, initial_state = _build_graph_and_state(scenario_data, lang, recorder)
    except Exception as e:
        await recorder.finish("failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
    return StreamingResponse(
        run_narrative_stream(scenario_data, seed_story, story_graph, initial_state, lang, recorder),
        media_type="text/event-stream",
        headers=headers,
    )


async def _continue_run_stream(run_id: int, headers: dict):
    """Pick an unfinished run back up: same memories, world state and run number; the AI writes on."""
    run = await run_recorder.library_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run #{run_id} not found")
    if not run["can_continue"]:
        raise HTTPException(status_code=409, detail=f"Run #{run_id} cannot be continued (finished, running, "
                                                    "or saved before continuing was possible)")
    scenario_data = await _load_scenario_or_404(run["scenario_id"])
    language = run["language"]
    if not await llm_available(scenario_data, language):
        message = (f"The AI is unavailable right now (daily quota used up or the service is busy), so run #{run_id} "
                   "can't be continued yet. It stays saved — try Continue again later.")
        return StreamingResponse(error_stream(message), media_type="text/event-stream", headers=headers)
    recorder = await RunRecorder.resume(run_id, scenario_data)
    if recorder is None:
        raise HTTPException(status_code=409, detail=f"Run #{run_id} is already running or cannot be continued")
    try:
        scenario_data, seed_story, story_graph, _, _ = _build_story(scenario_data, language, recorder)
        initial_state = StoryState.model_validate(recorder.saved["state"])
    except Exception as e:
        await recorder.finish("failed", turns=recorder.saved["turns"], error=f"Could not continue: {e}",
                              turn_count=len(recorder.saved["turns"]))
        raise HTTPException(status_code=500, detail=f"Could not continue run #{run_id}: {e}")
    return StreamingResponse(
        run_narrative_stream(scenario_data, seed_story, story_graph, initial_state, language, recorder,
                             previous_turns=recorder.saved["turns"]),
        media_type="text/event-stream",
        headers=headers,
    )


# ─────────────────────────────── Saved runs (player library) ───────────────────────────────

@app.get("/api/runs")
async def api_library(scenario: str | None = None, continuable: bool = False, limit: int = 50, offset: int = 0):
    """Saved runs for the player: every run with at least one turn, newest first. continuable=true → only unfinished."""
    return await run_recorder.library(scenario, continuable, limit, offset)


@app.get("/api/runs/{run_id}")
async def api_library_run(run_id: int):
    """One saved run (turns + ending) to play in the player."""
    run = await run_recorder.library_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run #{run_id} not found")
    return run


# ─────────────────────────────── Scenarios (public) ───────────────────────────────

@app.get("/api/scenarios")
async def api_list_scenarios():
    """List available scenarios for the story player."""
    return {"scenarios": await store.list_scenarios(), "default": scn.DEFAULT_SCENARIO_ID}


@app.get("/api/scenarios/{scenario_id}")
async def api_get_scenario_public(scenario_id: str):
    """Scenario info for the story player (characters, images, colors) — no prompts."""
    return scn.public_view(await _load_scenario_or_404(scenario_id))


@app.get("/api/images/{image_id}")
async def api_image(image_id: str):
    """An image stored in the database (uploaded from the admin panel or imported)."""
    found = await store.get_image(image_id)
    if not found:
        raise HTTPException(status_code=404, detail="Image not found")
    data, content_type = found
    return Response(content=data, media_type=content_type,
                    headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.get("/api/scenarios/{scenario_id}/images/{filename}")
def api_scenario_image(scenario_id: str, filename: str):
    """Legacy: an image file in scenarios/<id>/images/ (new uploads are stored in the database)."""
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
async def api_admin_meta():
    """Editor helpers: placeholders per prompt, TTS voices, colors, default settings, database status."""
    return {
        "prompts": scn.PROMPT_PLACEHOLDERS,
        "voices": scn.TTS_VOICES,
        "colors": scn.CHARACTER_COLORS,
        "default_settings": scn.DEFAULT_SETTINGS,
        "database": await db.ensure(),
        "llm_log": {"enabled": run_recorder.LLM_LOG_ENABLED, "retention_days": run_recorder.LLM_LOG_RETENTION_DAYS},
        "image_generation": image_generator.info(),
    }


@app.get("/api/admin/scenarios", dependencies=[Depends(require_admin)])
async def api_admin_list_scenarios():
    """All scenarios including drafts (the public list hides drafts)."""
    return {"scenarios": await store.list_scenarios(include_drafts=True), "default": scn.DEFAULT_SCENARIO_ID,
            "writable": store.writable()}


@app.post("/api/admin/scenarios/generate", dependencies=[Depends(require_admin)])
async def api_admin_generate_scenario(payload: dict = Body(...)):
    """
    "New with AI": stream progress while the model writes a full scenario from a short idea.
    Events: progress {message}, done {id, title, warnings}, error {message}. Saved as a draft.
    """
    if not await db.ensure():
        raise _http_error(store.ReadOnlyError())
    brief = str(payload.get("brief", ""))
    with_images = bool(payload.get("images", True)) and image_generator.enabled()
    try:
        num_characters = int(payload.get("num_characters", 4))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="num_characters must be a number")

    async def stream():
        try:
            async for event in scenario_generator.generate_scenario(brief, num_characters):
                if event["type"] == "done":
                    scenario = event["scenario"]
                    new_id = await store.unique_id(scenario["title"])
                    warnings = list(event["warnings"])
                    if with_images:
                        async for update in _generate_images_stream(new_id, scenario, warnings):
                            yield update
                    await store.save_scenario(new_id, scenario, note="Generated with AI", create=True)
                    print(f"[Generator] Saved draft scenario '{new_id}'")
                    yield f"data: {json.dumps({'type': 'done', 'id': new_id, 'title': scenario['title'], 'warnings': warnings})}\n\n"
                else:
                    yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            print(f"[Generator] Failed: {e!r}")
            yield f"data: {json.dumps({'type': 'error', 'message': scenario_generator.friendly_error(e)})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/admin/scenarios/import", dependencies=[Depends(require_admin)])
async def api_admin_import_scenario(payload: dict = Body(...)):
    """Import a scenario exported from this admin panel (or a plain scenario.json) as a new scenario."""
    try:
        return await store.import_scenario(payload)
    except Exception as e:
        raise _http_error(e)


@app.get("/api/admin/scenarios/{scenario_id}", dependencies=[Depends(require_admin)])
async def api_admin_get_scenario(scenario_id: str):
    return await _load_scenario_or_404(scenario_id)


@app.put("/api/admin/scenarios/{scenario_id}", dependencies=[Depends(require_admin)])
async def api_admin_save_scenario(scenario_id: str, payload: dict = Body(...)):
    try:
        return await store.save_scenario(scenario_id, payload)
    except Exception as e:
        raise _http_error(e)


@app.post("/api/admin/scenarios", dependencies=[Depends(require_admin)])
async def api_admin_create_scenario(payload: dict = Body(...)):
    """Create a scenario by copying an existing one (default: the built-in scenario)."""
    new_id = str(payload.get("id", "")).strip()
    source_id = payload.get("copy_from") or scn.DEFAULT_SCENARIO_ID
    try:
        scn._check_id(new_id)
        return await store.create_copy(new_id, source_id, payload.get("title"))
    except Exception as e:
        raise _http_error(e)


@app.delete("/api/admin/scenarios/{scenario_id}", dependencies=[Depends(require_admin)])
async def api_admin_delete_scenario(scenario_id: str):
    if scenario_id == scn.DEFAULT_SCENARIO_ID:
        raise HTTPException(status_code=400, detail="The default scenario cannot be deleted.")
    try:
        await store.delete_scenario(scenario_id)
    except Exception as e:
        raise _http_error(e)
    return {"deleted": scenario_id}


@app.get("/api/admin/scenarios/{scenario_id}/versions", dependencies=[Depends(require_admin)])
async def api_admin_versions(scenario_id: str):
    try:
        return {"versions": await store.list_versions(scenario_id)}
    except Exception as e:
        raise _http_error(e)


@app.get("/api/admin/scenarios/{scenario_id}/versions/{version}", dependencies=[Depends(require_admin)])
async def api_admin_version(scenario_id: str, version: int):
    try:
        return await store.get_version(scenario_id, version)
    except Exception as e:
        raise _http_error(e)


@app.post("/api/admin/scenarios/{scenario_id}/versions/{version}/restore", dependencies=[Depends(require_admin)])
async def api_admin_restore_version(scenario_id: str, version: int):
    try:
        return await store.restore_version(scenario_id, version)
    except Exception as e:
        raise _http_error(e)


@app.get("/api/admin/scenarios/{scenario_id}/export", dependencies=[Depends(require_admin)])
async def api_admin_export_scenario(scenario_id: str):
    try:
        data = await store.export_scenario(scenario_id)
    except Exception as e:
        raise _http_error(e)
    return Response(content=json.dumps(data, ensure_ascii=False, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{scenario_id}.scenario.json"'})


@app.post("/api/admin/scenarios/{scenario_id}/images", dependencies=[Depends(require_admin)])
async def api_admin_upload_image(scenario_id: str, payload: dict = Body(...)):
    """Upload an image as base64 ({filename, data}); stored in the database. Returns the URL to use."""
    await _load_scenario_or_404(scenario_id)
    filename = str(payload.get("filename", ""))
    if Path(filename).suffix.lower() not in ALLOWED_IMAGE_TYPES:
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
    try:
        return {"url": await store.save_image(scenario_id, filename, raw)}
    except Exception as e:
        raise _http_error(e)


# ─────────────────────────────── Admin: AI images ───────────────────────────────

async def _generate_images_stream(scenario_id: str, scenario: dict, warnings: list):
    """Draw the background and every character of a new scenario, yielding progress as SSE lines."""
    queue: asyncio.Queue = asyncio.Queue()

    async def progress(message: str):
        await queue.put(message)

    async def save(filename: str, raw: bytes) -> str:
        return await store.save_image(scenario_id, filename, raw)

    def sse(message: str) -> str:
        return f"data: {json.dumps({'type': 'progress', 'step': 'images', 'message': message})}\n\n"

    count = 1 + len(scenario.get("characters", []))
    yield sse(f"Drawing {count} images ({image_generator.MODEL.rsplit('/', 1)[-1]})…")
    task = asyncio.create_task(image_generator.generate_scenario_images(scenario, save, progress))
    while not (task.done() and queue.empty()):
        try:
            yield sse(await asyncio.wait_for(queue.get(), timeout=1))
        except asyncio.TimeoutError:
            pass
    warnings.extend(task.result())


@app.post("/api/admin/images/prompt", dependencies=[Depends(require_admin)])
async def api_admin_image_prompt(payload: dict = Body(...)):
    """Suggested prompt for a background ({target: 'background', scenario}) or a character (+ character)."""
    scenario = payload.get("scenario") or {}
    if payload.get("target") == "character":
        return {"prompt": image_generator.character_prompt(scenario, payload.get("character") or {})}
    return {"prompt": image_generator.background_prompt(scenario)}


@app.post("/api/admin/scenarios/{scenario_id}/images/generate", dependencies=[Depends(require_admin)])
async def api_admin_generate_image(scenario_id: str, payload: dict = Body(...)):
    """Generate an image from {prompt, target} and store it. Returns its URL; the scenario itself is not changed."""
    await _load_scenario_or_404(scenario_id)
    if not await db.ensure():
        raise _http_error(store.ReadOnlyError())
    try:
        raw = await image_generator.generate(str(payload.get("prompt", "")))
    except image_generator.ImageGenerationError as e:
        raise HTTPException(status_code=502 if image_generator.enabled() else 503, detail=str(e))
    kind = "character" if payload.get("target") == "character" else "background"
    return {"url": await store.save_image(scenario_id, f"ai-{kind}.jpg", raw)}


# ─────────────────────────────── Admin: story runs ───────────────────────────────

async def _require_runs_db() -> None:
    if not await db.ensure():
        raise HTTPException(status_code=503, detail="The database is not connected — story runs are unavailable.")


@app.get("/api/admin/runs", dependencies=[Depends(require_admin)])
async def api_admin_runs(scenario: str | None = None, status: str | None = None, language: str | None = None,
                         limit: int = 50, offset: int = 0):
    """Recorded story runs, newest first."""
    await _require_runs_db()
    return await run_recorder.list_runs(scenario, status, language, limit, offset)


@app.get("/api/admin/runs/{run_id}", dependencies=[Depends(require_admin)])
async def api_admin_run(run_id: int):
    """One run with every recorded event, in order."""
    await _require_runs_db()
    run = await run_recorder.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run #{run_id} not found")
    return run


@app.get("/api/admin/runs/{run_id}/llm-calls", dependencies=[Depends(require_admin)])
async def api_admin_run_llm_calls(run_id: int):
    """Every prompt and response of a run (kept for LLM_LOG_RETENTION_DAYS)."""
    await _require_runs_db()
    return {"calls": await run_recorder.get_llm_calls(run_id)}


@app.patch("/api/admin/runs/{run_id}", dependencies=[Depends(require_admin)])
async def api_admin_update_run(run_id: int, payload: dict = Body(...)):
    """Include or exclude a run from the offline replay pool."""
    await _require_runs_db()
    if "in_replay_pool" not in payload:
        raise HTTPException(status_code=422, detail="Send {\"in_replay_pool\": true|false}")
    if not await run_recorder.set_replay_pool(run_id, bool(payload["in_replay_pool"])):
        raise HTTPException(status_code=404, detail=f"Run #{run_id} not found")
    return await run_recorder.get_run(run_id)


@app.delete("/api/admin/runs/{run_id}", dependencies=[Depends(require_admin)])
async def api_admin_delete_run(run_id: int):
    await _require_runs_db()
    if not await run_recorder.delete_run(run_id):
        raise HTTPException(status_code=404, detail=f"Run #{run_id} not found")
    return {"deleted": run_id}
