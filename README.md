# GenAI_DSS: Multi-Agent Narrative System

## 1. Introduction

A **Multi-Agent Narrative System** built for the **Hackfest x Datathon 2026** Generative AI module. The system uses **LangGraph** to orchestrate autonomous character agents that navigate a conflict-driven story defined by a "Story Seed."

Unlike traditional chatbots, these agents possess:
- **Individual Memory** — each character tracks what they've seen, heard, and done across turns.
- **Open-Ended Physical Actions** — agents perform any realistic action (not from a fixed menu) that changes the world state.
- **Deep Psychological Personas** — each character has a complete psychology, background, fears, strategies, and tactical evolution that guides their behavior across turns.
- **Structured Reasoning** — agents "think" through their goals before deciding whether to talk, act, or both.
- **LLM-Generated Story Twists** — the Director agent generates context-aware dramatic complications mid-story, unique every run.
- **Reviewer Agent** — a fifth agent checks each character turn for Karachi realism, logical consistency, and repetition; rejected turns get one retry with the reviewer's suggestion.
- **Real-Time Frontend** — React frontend with SSE streaming shows turns as they are generated.

## 2. Setup

### Prerequisites
- Python 3.11+
- `uv` package manager
- Node.js 18+ (for frontend)
- Google API Key (Gemini Free Tier)

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Noman37375/GenAi_DSS_Quadgentics.git
   cd GenAi_DSS_Quadgentics
   ```

2. **Install backend dependencies**:
   ```bash
   uv sync
   ```

3. **Install frontend dependencies**:
   ```bash
   cd Hackthon_Frontend_IBA/frontend
   npm install
   cd ../..
   ```

4. **Environment Configuration**:
   Create a `.env` file in the root directory:
   ```ini
   GOOGLE_API_KEY=your_api_key_here
   ```

**First-time run checklist:** Ensure `GOOGLE_API_KEY` is set in `.env`, then from repo root run `npm run dev` (for frontend + API) or `uv run python src/main.py` (backend only). Open http://localhost:5173 for the app or check terminal for narrative output.

### Troubleshooting

| Issue | Fix |
|-------|-----|
| `GOOGLE_API_KEY` missing or invalid | Create `.env` in repo root with `GOOGLE_API_KEY=your_key`. Get a key from [Google AI Studio](https://aistudio.google.com/app/apikey) (free tier). |
| `uv: command not found` | Install [uv](https://docs.astral.sh/uv/): `pip install uv` or use your OS package manager. |
| Port 8000 or 5173 already in use | Stop the process using that port, or change port in `package.json` (dev:api) / Vite config (frontend). |
| Backend runs but frontend shows "Connection lost" | Ensure API is running (`npm run dev:api` or `npm run dev`). Frontend expects `http://localhost:8000` (set `VITE_API_URL` in frontend `.env` if your API is elsewhere). |
| `ModuleNotFoundError` or import errors | Run from **repo root** (where `src/` and `pyproject.toml` are). Use `uv run python src/main.py` not `python main.py` from inside `src/`. |

## 3. Usage

### Run Backend + Frontend Together
```bash
npm run dev
```
This starts both the FastAPI backend (port 8000) and Vite frontend (port 5173) using `concurrently`.

### Run Backend Only (CLI mode)
```bash
uv run python src/main.py
```
(Run from repo root so `src` and `examples` resolve.)

### Run Backend API Only
```bash
npm run dev:api
```

### Run Frontend Only
```bash
npm run dev:frontend
```

The system will:
1. Load the seed story and character configurations from `examples/rickshaw_accident/`.
2. Initialize 4 character agents + 1 Director agent + 1 Reviewer agent.
3. Run the narrative loop (15-25 turns) with open-ended actions, memory updates, an LLM-generated twist, and per-turn reviewer checks.
4. Generate `story_output.json` and `prompts_log.json`.
5. Stream each turn to the frontend in real-time via SSE.

## 4. System Architecture

### 4.1 Multi-Agent Design

The system follows a **Director-Agent** architecture orchestrated by a LangGraph `StateGraph`:

```
┌───────────────────────────────────────────────────────────┐
│                    NarrativeGraph                          │
│                 (LangGraph StateGraph)                     │
│                                                           │
│  ┌──────────────┐   ┌────────────────┐   ┌────────────┐  │
│  │  Director     │──>│ Character Agent │──>│  Reviewer   │  │
│  │  Selects      │   │ Responds (with  │   │  (Karachi   │  │
│  │  Speaker +    │   │ reasoning,      │   │  realism    │  │
│  │  Narrates     │   │ dialogue,       │   │  check)     │  │
│  │  scene        │   │ open-ended      │   └──────┬─────┘  │
│  └──────┬───────┘   │ action)         │    retry if reject │
│         │           └────────┬───────┘          │         │
│         │                    │                   │         │
│         ▼                    ▼                   │         │
│  ┌───────────────────────────────┐               │         │
│  │     Check Conclusion          │               │         │
│  │  (min turns, min actions,     │               │         │
│  │   post-twist breathing room)  │               │         │
│  └────────────┬──────────────────┘               │         │
│               │                                  │         │
│     continue ─┤── conclude ──> END               │         │
│               │                                  │         │
│  ┌────────────▼────────────────┐                 │         │
│  │ LLM-Generated Twist @ Turn 9│                 │         │
│  │ (Director generates unique   │                 │         │
│  │  context-aware complication)  │                │         │
│  └──────────────────────────────┘                │         │
│                                                  │         │
│  Memory updates + World State after each turn    │         │
│  Action validation + pattern-based execution     │         │
└───────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────┐
│                   Frontend + API                          │
│                                                           │
│  FastAPI (src/api.py)          React (Vite)               │
│  - POST /api/run               - SSE EventSource          │
│  - GET /api/story              - Turn-by-turn display     │
│  - GET /api/run/stream (SSE)   - Auto-advance on new turn │
└───────────────────────────────────────────────────────────┘
```

### 4.2 Agent Roles

| Agent | Role | Key Capability |
|---|---|---|
| **Director** | Orchestrator | Selects speakers, narrates scenes, generates twists, checks conclusion |
| **4 Character Agents** | Autonomous actors | Each has deep psychological persona, memory, reasoning, open-ended actions |
| **Reviewer** | Quality gate | Checks each turn for Karachi realism, language, logic, repetition |

## 5. Implemented Features

### 5.1 Character Memory System
Each character maintains an individual memory buffer (sliding window of 20 entries) that tracks:
- What they said and did in previous turns
- What other characters said and did (cross-character propagation)
- World events and story twists

Memory is stored in `StoryState.character_memories` as per-character lists and fed into each character's prompt.

### 5.2 Open-Ended Action System

**Design Philosophy**: Rather than restricting characters to a fixed menu of actions, the system allows **any realistic physical action**. Characters can grab keys, throw money, sit on the ground, block a path, make a phone call, push someone, wave down a passerby — anything a real person would do on a Karachi street.

The system uses **pattern-matching** to categorize actions for world-state tracking:

| Pattern | World State Effect | Example |
|---|---|---|
| money/pay/give | `money_exchanged`, `money_from`, `money_to` | `Give_Money → Ahmed Malik` |
| bribe/chai_pani | `bribe_offered`, `bribe_from`, `bribe_to` | `Offer_Bribe → Constable Raza` |
| challan/ticket/fine | `challan_written`, `challan_target` | `Write_Challan → Saleem` |
| key/confiscate/snatch | `keys_confiscated`, `keys_taken_from` | `Grab_Keys → Ahmed Malik` |
| record/video/film | `being_recorded`, `recorder` | `Record_Video` |
| block/stand_in_front | `vehicle_blocked`, `vehicle_blocked_by` | `Block_Path → Ahmed Malik` |
| push/shove/grab | `physical_confrontation_{actor}` | `Push_Away → Constable Raza` |
| call/phone/dial | `{actor}_made_call` | `Call_Lawyer` |
| sit/ground/collapse | `{actor}_on_ground` | `Sit_On_Road` |
| cry/wail/sob | `{actor}_crying` | `Break_Down_Crying` |
| *(any other)* | `action_{type}_{actor}` | `Tear_Document`, `Wave_Down_Taxi` |

Validation only checks: action is non-empty, target (if given) exists in character profiles, and actor is not targeting themselves.

### 5.3 Deep Psychological Personas

Each character has a complete psychological profile that drives behavior:

- **Saleem** (rickshaw driver): Street-smart poverty psychology. 95% Roman Urdu. Knows when to cry, when to get angry, when to play the victim. Tactical evolution from shock → anger → strategy → negotiation across turns.
- **Ahmed Malik** (businessman): Elite Karachiite psychology. English-Urdu code-switching. Oscillates between authority and fear of the crowd. Evolution from dismissive → frustrated → panicked → resigned.
- **Constable Raza** (traffic cop): Corrupt but cunning. 90% blunt street Urdu. Sees every situation as revenue. Plays both sides. Fear of cameras and DSP. Evolution from assessment → squeezing → negotiation → self-preservation.
- **Uncle Jameel** (shopkeeper elder): Lives for drama. 95% dramatic Urdu. Self-appointed mediator. Sides with the poor but presents as fair. Evolution from dramatic arrival → mediation → taking sides → brokering the deal.

Each persona includes explicit "WHAT YOU WOULD NEVER DO" rules and turn-range tactical evolution guidelines.

### 5.4 Reasoning Layer
Characters respond with structured JSON containing:
```json
{
    "reasoning": "Internal thought about strategy and what has changed",
    "decision": "talk | act | both",
    "dialogue": "Spoken words in character voice",
    "action": {
        "type": "Free-form label (e.g., Grab_Keys, Sit_On_Road, Throw_Money)",
        "target": "character name or null",
        "description": "Vivid description of the physical action"
    }
}
```
The `reasoning` field captures the agent's internal decision-making — forcing chain-of-thought before speaking or acting.

### 5.5 LLM-Generated Story Twists

At turn 9, the **Director agent generates a unique, context-aware twist** via a dedicated LLM call (`DIRECTOR_TWIST_PROMPT`). The twist:
- Is based on everything that has happened in the story so far
- Is realistic for a Karachi street scene
- Changes the dynamic for at least 2 characters
- Cannot be ignored — characters must react

Each run produces a **different twist** because it's generated from context, not selected from a fixed list. Examples from actual runs: "dhaba gas cylinder explosion nearby", "senior officer spotted approaching", "mechanic discovers hidden damage."

Twists update `world_state` and inject into ALL characters' memories, with 5-turn post-twist breathing room before conclusion is allowed.

### 5.6 Reviewer Agent

A fifth agent runs after each character turn, acting as a "born-and-raised Karachiite" quality gate. It checks:

1. **Language realism** — Saleem must not speak like a lawyer; Raza must sound blunt, not polite; Ahmed must code-switch naturally.
2. **Logical consistency** — Would a man earning 800/day refuse 20,000? Are damage amounts realistic (rickshaw bumper: 2,000-5,000, not 50,000)?
3. **Repetition** — Same emotional appeal or argument repeated? Same tactic with different words?
4. **Action logic** — Does the physical action fit the current moment?

If the reviewer rejects (major severity), the character gets **one retry** with the reviewer's suggestion appended to context. All reviewer calls are logged in `prompts_log.json`.

### 5.7 Director Intelligence
- **Story Phase System**: Setup (1-4) → Escalation (5-9) → Complication (10-15) → Resolution (16-22)
- **Anti-Consecutive**: Code-level enforcement prevents same character speaking twice in a row
- **Anti-Ping-Pong**: Detects when 2 characters dominate for 4+ turns and forces a third
- **Conclusion Resistance**: min_turns (15), min_actions (5), post-twist breathing room (5 turns), even-turn checks before turn 18, max_turns (25) hard cap

### 5.8 FastAPI Backend + React Frontend

**Backend** (`src/api.py`):
- `POST /api/run` — Run full narrative, return frontend-shaped payload
- `GET /api/story` — Return last story (200 with empty payload when none)
- `GET /api/run/stream` — SSE streaming: each reviewed turn sent as it's generated

**Frontend** (`Hackthon_Frontend_IBA/frontend/`):
- EventSource for real-time SSE streaming
- Turn-by-turn display with character avatars
- Auto-advance when new turn arrives during streaming
- Next button disabled while waiting for next turn
- Shows narration, dialogue, and action text per turn

## 6. Documentation and Deliverables

| Deliverable | Location | PDF (for submission) |
|-------------|----------|----------------------|
| **README** | This file | — |
| **Technical Report** | `Technical_Report.md` | Generate PDF: `pandoc Technical_Report.md -o Technical_Report.pdf` (requires [pandoc](https://pandoc.org/)). Alternatively use the provided `Technical_Report.tex` with `pdflatex Technical_Report.tex`. |

The problem statement asks for a PDF (LaTeX) technical report. We provide the report in Markdown and LaTeX source; use the commands above to produce the PDF. A pre-built `Technical_Report.pdf` may be included in the submission package.

## 7. Output Files

**`story_output.json`** — Final narrative trace:
- `title`, `seed_story` (metadata)
- `events[]` — chronological list with `type` (dialogue/narration/action), `speaker`, `content`, `turn`
- `conclusion` — why the story ended
- `metadata` — total turns, total actions, conclusion reason

**`prompts_log.json`** — Debug/audit log:
- `timestamp`, `agent`, `prompt`, `response` for every LLM call (Director, Character, Reviewer)

## 8. Configuration

| Parameter | Default | Description |
|---|---|---|
| `model_name` | `gemma-3-27b-it` | LLM model (Google Generative AI free tier) |
| `temperature` | `0.75` | Slightly higher for creative, varied output |
| `max_turns` | `25` | Maximum dialogue turns |
| `min_turns` | `15` | Minimum before conclusion allowed |
| `max_tokens_per_prompt` | `2000` | Max generation tokens |
| `max_context_length` | `4000` | Max input context |
| `max_consecutive_same_character` | `1` | Anti-repetition threshold |
| `num_characters` | `4` | Number of character agents |

## 9. Features Beyond Requirements

The problem statement requires Memory, Actions, and Reasoning. Our system adds **8 novel extensions**:

| # | Feature | Description |
|---|---|---|
| 1 | **Reviewer Agent** | 6th agent validates every turn for Karachi realism, language, logic, repetition |
| 2 | **Deep Psychological Personas** | Multi-paragraph character psychology with tactical evolution per turn range |
| 3 | **LLM-Generated Twists** | Director creates unique context-aware twist each run (not from a fixed list) |
| 4 | **Open-Ended Actions** | 13-category pattern-matching on free-form actions + catch-all |
| 5 | **3-Layer Anti-Repetition** | Code + context + reviewer prevents repetition at every level |
| 6 | **5-Mechanism Conclusion Resistance** | min_turns, min_actions, post-twist buffer, gating, max_turns |
| 7 | **4-Phase Story Structure** | Director follows Setup → Escalation → Complication → Resolution |
| 8 | **Real-Time Frontend + SSE** | React app streams turns live via Server-Sent Events |

## 10. Key Files

| File | Purpose |
|---|---|
| `src/main.py` | CLI entry point — loads config, initializes agents, runs graph |
| `src/api.py` | FastAPI server — POST /api/run, GET /api/story, GET /api/run/stream (SSE) |
| `src/schemas.py` | Pydantic models: `StoryState`, `CharacterProfile`, `DialogueTurn`, `Action` |
| `src/config.py` | Configuration: turns, temperature, model settings |
| `src/actions.py` | Open-ended action validation + pattern-based execution + world-state updates |
| `src/story_state.py` | StoryStateManager — initializes characters, memory, goals, inventory |
| `src/graph/narrative_graph.py` | LangGraph workflow: director → character → reviewer → conclusion loop, twist injection |
| `src/agents/base_agent.py` | BaseAgent with LLM integration (Google GenAI) + prompt/response logging |
| `src/agents/character_agent.py` | CharacterAgent — structured JSON reasoning + dialogue + action |
| `src/agents/director_agent.py` | DirectorAgent — speaker selection, twist generation, conclusion checking |
| `src/agents/reviewer_agent.py` | ReviewerAgent — Karachi realism, language, repetition, action logic checks |
| `src/prompts/character_prompts.py` | Deep psychological personas with tactical evolution per character |
| `src/prompts/director_prompts.py` | Director prompts: speaker selection, twist generation, conclusion |
| `examples/rickshaw_accident/seed_story.json` | Story seed with setting details (vehicles, location, weather) |
| `examples/rickshaw_accident/character_configs.json` | 4 character profiles with goals, inventory, descriptions |
| `Hackthon_Frontend_IBA/frontend/` | React + Vite frontend for real-time story viewing |
