"""
FastAPI server for the narrative system.
POST /api/run: run full narrative once, store result, return frontend-shaped payload.
GET /api/story: return last stored story (for refresh / load without re-run).
"""
import asyncio
import io
import json
import os
import sys
from pathlib import Path

current_dir = Path(__file__).parent
project_root = current_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import edge_tts
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from src.schemas import StoryState

from src.config import StoryConfig
from src.agents.character_agent import CharacterAgent
from src.agents.director_agent import DirectorAgent
from src.agents.reviewer_agent import ReviewerAgent
from src.graph.narrative_graph import NarrativeGraph
from src.story_state import StoryStateManager

# In-memory store for the last run (frontend-shaped payload)
last_story: dict | None = None

# Per-character voice profiles — same base voice, different pitch/rate for distinct feel
# Saleem: faster, slightly lower (desperate, rushed)
# Ahmed: slower, slightly higher (arrogant, measured)
# Raza: default speed, lower pitch (gruff, commanding)
# Jameel: fastest, higher pitch (theatrical, dramatic uncle energy)
SPEAKER_VOICE_PROFILES = {
    "Saleem":         {"voice": "hi-IN-MadhurNeural", "rate": "+15%", "pitch": "-4Hz"},
    "Ahmed Malik":    {"voice": "hi-IN-MadhurNeural", "rate": "-15%", "pitch": "+6Hz"},
    "Constable Raza": {"voice": "hi-IN-MadhurNeural", "rate": "+0%",  "pitch": "-10Hz"},
    "Uncle Jameel":   {"voice": "hi-IN-MadhurNeural", "rate": "+25%", "pitch": "+10Hz"},
}
DEFAULT_VOICE_PROFILE = {"voice": "hi-IN-MadhurNeural", "rate": "+0%", "pitch": "+0Hz"}

SPEAKER_TO_CHARACTER = {
    "Saleem": "saleem",
    "Ahmed Malik": "ahmed",
    "Constable Raza": "raza",
    "Uncle Jameel": "jameel",
}


def events_to_frontend_turns(events: list, seed_story: dict, conclusion_reason: str | None) -> dict:
    """
    Transform backend events + seed_story + conclusion into frontend payload.
    Returns { title, scenario, turns, conclusion }.
    """
    title = seed_story.get("title", "The Rickshaw Accident")
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
            character = SPEAKER_TO_CHARACTER.get(speaker, speaker.lower().replace(" ", "_")[:10])
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


async def run_narrative(language: str = "urdu"):
    """Run the full narrative. Returns (final_state, seed_story, director, reviewer, characters)."""
    examples_dir = project_root / "examples" / "rickshaw_accident"
    seed_story = json.loads((examples_dir / "seed_story.json").read_text())
    char_configs = json.loads((examples_dir / "character_configs.json").read_text())

    config = StoryConfig(language=language)
    characters = [
        CharacterAgent(name=char["name"], config=config)
        for char in char_configs["characters"]
    ]
    director = DirectorAgent(config)
    reviewer = ReviewerAgent(config)
    story_manager = StoryStateManager(seed_story, char_configs["characters"], config)
    story_graph = NarrativeGraph(config, characters, director, reviewer)

    final_state = await story_graph.run(
        seed_story=seed_story,
        character_profiles=story_manager.state.character_profiles,
        character_memories=story_manager.state.character_memories,
    )
    return final_state, seed_story, director, reviewer, characters


def _build_graph_and_state(language: str = "urdu"):
    """Build narrative graph and initial state (for streaming). Returns (seed_story, story_graph, initial_state)."""
    examples_dir = project_root / "examples" / "rickshaw_accident"
    seed_story = json.loads((examples_dir / "seed_story.json").read_text())
    char_configs = json.loads((examples_dir / "character_configs.json").read_text())
    config = StoryConfig(language=language)
    characters = [
        CharacterAgent(name=char["name"], config=config)
        for char in char_configs["characters"]
    ]
    director = DirectorAgent(config)
    reviewer = ReviewerAgent(config)
    story_manager = StoryStateManager(seed_story, char_configs["characters"], config)
    story_graph = NarrativeGraph(config, characters, director, reviewer)
    initial_state = StoryState(
        seed_story=seed_story,
        character_profiles=story_manager.state.character_profiles,
        character_memories=story_manager.state.character_memories,
        world_state=story_manager.state.world_state,
    )
    return seed_story, story_graph, initial_state


async def run_narrative_stream(seed_story: dict, story_graph: NarrativeGraph, initial_state: StoryState):
    """
    Stream graph steps; after each character_respond we have new events.
    Yields SSE payloads: meta, newTurns (per turn), conclusion, done.
    """
    global last_story
    title = seed_story.get("title", "The Rickshaw Accident")
    scenario = seed_story.get("description", "")
    yield f"data: {json.dumps({'type': 'meta', 'title': title, 'scenario': scenario})}\n\n"
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
                payload = events_to_frontend_turns(events, seed_story, None)
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
    last_story = {"title": title, "scenario": scenario, "turns": all_turns, "conclusion": conclusion_reason}
    yield f"data: {json.dumps({'type': 'done'})}\n\n"


app = FastAPI(title="AI Narrative Engine API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/tts")
async def api_tts(text: str, speaker: str = ""):
    """Generate TTS with per-character voice profile (pitch + rate)."""
    profile = SPEAKER_VOICE_PROFILES.get(speaker, DEFAULT_VOICE_PROFILE)
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
async def api_run(lang: str = "urdu"):
    """Run the full narrative once, store result, return frontend-shaped payload."""
    global last_story
    try:
        final_state, seed_story, director, reviewer, characters = await run_narrative(language=lang)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    events = final_state.get("events", [])
    conclusion_reason = final_state.get("conclusion_reason")
    payload = events_to_frontend_turns(events, seed_story, conclusion_reason)
    last_story = payload

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
async def api_run_stream(lang: str = "urdu"):
    """
    Run the narrative and stream each reviewed turn as SSE.
    Events: meta (title, scenario), turns (newTurns), conclusion, done.
    """
    try:
        seed_story, story_graph, initial_state = _build_graph_and_state(language=lang)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return StreamingResponse(
        run_narrative_stream(seed_story, story_graph, initial_state),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
