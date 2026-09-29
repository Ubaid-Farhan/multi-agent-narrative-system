# Multi-Agent Narrative System

**AI characters that argue, bargain, cry, bribe and improvise their way through a live street scene. Every run is a new story.**

You describe a situation, for example *a rickshaw hits a BMW on Shahrah-e-Faisal, Karachi*. A cast of autonomous LLM agents plays it out turn by turn. Each agent has its own psychology, memory, goals and inventory. A **Director** agent narrates the scene and decides who speaks next, a **Reviewer** agent rejects lines that don't sound real, and the scene streams live to a web player with a different voice for each character.

Everything the agents see (story, characters, personas, prompts, settings, images) is stored in **Postgres** and edited in an **admin panel**, with full version history. An AI can write a whole new scenario from a single sentence. **Every story run is recorded step by step**: each narration, dialogue with the character's hidden reasoning, reviewer verdict, action, world state and LLM prompt. Completed runs are replayed when the LLM is down.

---

## Table of contents
1. [Highlights](#1-highlights)
2. [How a story runs](#2-how-a-story-runs)
3. [Quick start](#3-quick-start)
4. [The story player](#4-the-story-player)
5. [The admin panel](#5-the-admin-panel)
6. [New scenario with AI](#6-new-scenario-with-ai)
7. [Database, run records & offline replay](#7-database-run-records--offline-replay)
8. [LLM models & resilience](#8-llm-models--resilience)
9. [The story engine in depth](#9-the-story-engine-in-depth)
10. [Configuration reference](#10-configuration-reference)
11. [Scenario file format](#11-scenario-file-format)
12. [API reference](#12-api-reference)
13. [Project structure](#13-project-structure)
14. [Deployment](#14-deployment)
15. [Troubleshooting](#15-troubleshooting)

---

## 1. Highlights

| | Feature | What it means |
|---|---|---|
| 🎭 | **Autonomous character agents** | Each character has a multi-paragraph persona (psychology, language register, tactics that change over the scene, a comic flaw, forms of address, hard "never do" rules), plus goals, inventory and a personal memory. |
| 🎬 | **Director agent** | Picks who speaks next, narrates the scene with fresh sensory detail each turn, follows a 4-phase story arc, and decides when the story has earned its ending. |
| 🌀 | **AI-generated twists** | At a set turn the Director invents a context-aware complication from what has happened so far, so every run gets a different twist. |
| 🧐 | **Reviewer agent** | Checks every turn for realism, language register, logic and repetition. A rejected turn is regenerated once with the Reviewer's feedback. |
| ✋ | **Open-ended actions** | Characters can do *anything* physical (grab keys, sit on the road, throw money, call a lawyer), and actions update a shared world state. |
| 🔴 | **Live streaming player** | Turns stream in over Server-Sent Events, with typewriter dialogue, per-character TTS voices, auto-play, Roman Urdu / English modes and a scenario picker. |
| 🛠️ | **Admin panel** | Edit every story, character, persona and prompt from the browser. Placeholders are validated before saving, images are uploaded to the database, every save is versioned, and scenarios can be exported and imported. |
| ✨ | **New with AI** | Turn a one-line idea into a complete, production-ready scenario (characters, deep personas and every prompt), using your own **gpt-oss** server. |
| 💾 | **Everything in Postgres (Neon)** | Scenarios, characters, prompts, images and version history live in the database. JSON files in `scenarios/` are kept in sync as a backup. |
| 📜 | **Every run recorded** | Each run gets a run number and a full timeline in admin → **Stories**: narration, twist, dialogue + reasoning, rejected drafts, reviewer verdicts, actions, world state, ending, and every LLM prompt/response. |
| ♻️ | **Offline replay** | If the API key fails or the quota runs out, a completed run is replayed exactly as it was, turn by turn. |
| 🛡️ | **Resilient LLM chain** | Gemini → backup Gemini models → OpenAI, with retries on rate limits, overload and network errors. |

---

## 2. How a story runs

```
                ┌──────────────────────── NarrativeGraph (LangGraph) ─────────────────────────┐
                │                                                                             │
 scenario.json  │   ┌──────────────┐     ┌──────────────────┐     ┌──────────────┐            │
 (story, cast,  │   │   Director   │────▶│ Character agent  │────▶│   Reviewer   │            │
  personas,  ──▶│   │ picks speaker│     │ reasoning +      │     │ realism /    │── reject ─┐│
  prompts,      │   │ + narrates   │     │ dialogue +       │     │ logic /      │  (1 retry)││
  settings)     │   │ (+ twist at  │     │ free-form action │◀────│ repetition   │◀──────────┘│
                │   │  twist turn) │     └────────┬─────────┘     └──────────────┘            │
                │   └──────▲───────┘              │ memory + world state updated              │
                │          │                      ▼                                           │
                │          │  continue   ┌──────────────────┐   conclude                      │
                │          └─────────────│ Check conclusion │──────────▶ ending narration     │
                │                        └──────────────────┘                                 │
                └─────────────────────────────────────────────────────────────────────────────┘
                        │ each reviewed turn                              │ completed story
                        ▼                                                 ▼
               FastAPI  /api/run/stream (SSE)  ──────▶  React player      Neon Postgres (replay when LLM is down)
```

1. The API loads a scenario (`scenarios/<id>/scenario.json`) and builds one agent per character, plus a Director and a Reviewer.
2. **Director** reads the world state and recent dialogue, then picks the next speaker and writes the scene narration.
3. **Character** gets its persona, goals, inventory, memory, what it already said and did, and which appeals the crowd is tired of. It replies with JSON: `reasoning`, `decision` (talk / act / both), `dialogue`, `action`.
4. **Reviewer** approves or rejects. On a major rejection the character regenerates once with the feedback.
5. The action is validated and applied to the **world state**, and every character's **memory** is updated.
6. **Conclusion check** ends the story only when it has been earned (see [9.6](#96-conclusion-rules)).
7. Each turn streams to the browser as it is produced. When the story completes, it is saved to the database.

---

## 3. Quick start

### Prerequisites
- **Python 3.11+** and [**uv**](https://docs.astral.sh/uv/)
- **Node.js 18+**
- A **Google Gemini API key** (free tier works): [Google AI Studio](https://aistudio.google.com/app/apikey)
- Optional: a Postgres database ([Neon](https://neon.tech) free tier recommended), an OpenAI key, a gpt-oss server

### Install
```bash
git clone https://github.com/fun33333/multi-agent-narrative-system.git
cd multi-agent-narrative-system

uv sync                                   # Python dependencies
npm install                               # root tools (concurrently)
cd frontend && npm install && cd ..       # React app
```

### Configure
```bash
cp .env.example .env
```
Then set at least:
```ini
GOOGLE_API_KEY=your_gemini_key
ADMIN_PASSWORD=choose-a-strong-password     # enables /admin
DATABASE_URL=postgresql://...               # scenarios, admin edits, images, every run, offline replay
```
All options are listed in the [configuration reference](#10-configuration-reference).

### Run
```bash
npm run dev
```
| Service | URL |
|---|---|
| Story player | http://localhost:5173 |
| Admin panel | http://localhost:5173/admin |
| API | http://localhost:8080 |

Other ways to run:
```bash
npm run dev:api                                   # API only (port 8080)
npm run dev:frontend                              # frontend only
uv run python src/main.py                         # terminal only, default scenario
uv run python src/main.py empty_buffet            # terminal only, another scenario
```

> **Using a different API port?** For example, if something else already uses 8080:
> `uv run uvicorn src.api:app --reload --port 8081`, and create `frontend/.env` with `VITE_API_URL=http://localhost:8081`.

---

## 4. The story player

The start screen is a menu with three choices:

| Option | What happens |
|---|---|
| **Continue** | Shown when the selected scenario has an unfinished run (the AI stopped, the browser closed, the server restarted). The AI picks the **same run** back up from its last saved turn, with the same memories and world state, and the player jumps straight to that turn. |
| **New story** | Pick a **scenario** (Kahani) and a **language** (Roman Urdu or English). The AI writes a brand-new story. |
| **Purani stories** | Every saved run, newest first, for this scenario or all of them. Each shows **Poori** (complete) or **Adhoori** (unfinished), its turn count, language and date. **Play** watches it again; **Continue** is available on unfinished runs. |

- **Live streaming:** turns appear as soon as the agents produce them (SSE).
- **Scene view:** a full-screen background, the speaking character's image and name, and the Director's narration (expandable).
- **Typewriter dialogue:** lines type out and any physical action is shown under the dialogue.
- **Voices:** "Listen" reads the line aloud with the character's own voice, speed and pitch (Microsoft Edge TTS).
- **Auto-play:** plays every turn with audio and advances by itself.
- **Navigation:** Prev / Next, a progress bar and turn dots, plus a replay button.
- **Character cards:** the whole cast along the bottom, with the current speaker highlighted.
- **No images yet?** Characters without an image show coloured initials, and scenarios without a background get a plain dark scene.
- **Menu** (🏠 in the controls, or after the ending) goes back to the start menu at any time.

---

## 5. The admin panel

Open **`/admin`** and log in with `ADMIN_PASSWORD`. If the variable is not set, the panel is disabled. Sessions last 12 hours, and changing the password logs everyone out.

| Tab | What you can edit |
|---|---|
| **Story** | Status (Draft / Published), title, subtitle, story seed, setting details (JSON), background image |
| **Characters** | Add or remove characters (minimum 2). Per character: name, display label, key, image upload, colour, short description, goals, inventory, **deep persona**, English-mode style, Reviewer notes (Urdu / English), repeated-appeal keywords, TTS voice / speed / pitch |
| **Prompts** | All 9 templates: character main prompt, Roman Urdu rule, English rule, Director (pick speaker, twist, conclusion), Reviewer (Urdu, English), fallback ending. Placeholders can be inserted with one click. |
| **Settings** | Max / min turns, twist turn, turns after twist, minimum physical actions, dialogue length, temperature |
| **History** | Every saved version of the scenario, with a note ("Saved from admin panel", "Generated with AI", "Restored version 3"…). View any version and **Restore** it; a restore is saved as a new version, so nothing is ever lost |

**Safety checks**
- A prompt can't be saved with an unknown placeholder, a missing required placeholder, or broken `{ }` braces. This is checked in the browser and again on the server.
- Unsaved changes are flagged, and the panel asks before you leave or switch scenarios.
- The default scenario (`rickshaw_accident`) cannot be deleted.

**Scenarios**
- **New** copies the current scenario, including its images.
- **✨ New with AI** writes a brand new one (next section).
- **Export** downloads a scenario as one JSON file with its images embedded; **Import** loads such a file (or a plain `scenario.json`) as a new scenario.
- **Drafts** stay hidden from the player until their status is set to **Published**.
- Changes are saved to the database and apply to the **next** story run, with no restart needed.

**Stories** (switch at the top of the panel)
- A list of every run: run number, scenario, language, status, turns, whether it's in the replay pool. Filter by scenario, status (completed / incomplete / failed / aborted / running) and language.
- Open a run to see its **timeline**, grouped by turn: the Director's narration and who it chose (and any anti-repetition override), the twist, each character's line with its **hidden reasoning** and decision, drafts the Reviewer rejected and why, actions (including rejected ones), the world state after each turn, the Director's conclusion checks, the ending and any errors.
- **As shown to viewers** shows the final story; **LLM prompts** shows every prompt and response with model and latency.
- Include or exclude a run from the offline replay pool, export it as JSON, or delete it. A run that is still generating updates live.

**Without a database** the panel opens read-only (a banner explains why): scenarios come from the backup JSON files and nothing can be saved.

---

## 6. New scenario with AI

Click **✨ New with AI** and describe a scene in a line or two, in Roman Urdu or English:

> *Lahore ki shaadi mein khana waqt se pehle khatam ho gaya. Dulhe ka baap, caterer, dulhan ki phuppo aur photographer aamne saamne.*

Choose the number of characters (2–6). The AI then writes **everything**:

| Generated | Details |
|---|---|
| Story | Title, subtitle (exact location), a 120–180 word story seed, setting details |
| Dramatic engine | Core conflict, why nobody can leave, what the resolution is paid in, possible complications |
| Characters | Name, label, description, goals, inventory, leverage, vulnerability, voice (gender-appropriate, with distinct speed and pitch), colour |
| Deep personas | 350–550 words each, in the same structure as the built-in characters: psychology, language, tactics in four turn bands, situational intelligence, flaw, forms of address, "never do" rules. Also English style, appeal keywords and Reviewer notes |
| Prompts | Director, Reviewer and character prompts rewritten for the new scene, with every placeholder kept intact |

**How quality is kept high**
- The built-in **Rickshaw scenario is shown to the model as the reference** it has to match in depth and specificity.
- The work is split into focused steps: blueprint → one call per character (in parallel) → one call per prompt (in parallel).
- Every output is **checked automatically**, including required persona sections, minimum length, appeal format, placeholders and JSON braces. Anything that fails is sent back to the model with the exact problem, up to 2 times.

**Model:** your self-hosted **gpt-oss** server (`GPT_OSS_BASE_URL`). If that server is down, **Gemini** is used with its *own* models (`gemini-3.5-flash`, then lite models), so the story models' daily quota is untouched. Paid OpenAI is never used by the generator.

Progress streams into the dialog, and a run takes about 1–7 minutes. The result opens as a **Draft**: add images, review it, set Status to **Published**, and save.

---

## 7. Database, run records & offline replay

Set `DATABASE_URL` (any Postgres; Neon recommended). On startup the API brings the schema up to date with **Alembic** migrations, then imports anything it doesn't have yet.

**What is stored**

| Table | Contents |
|---|---|
| `scenarios` | Title, subtitle, story seed, setting, background image, status, story settings, current version |
| `characters` | One row per character: persona, English style, goals, inventory, appeals, reviewer notes, voice, image, colour, order |
| `prompts` | The 9 prompt templates of each scenario |
| `images` | Image files themselves (served at `/api/images/<id>`; identical files are stored once) |
| `scenario_versions` | A full snapshot of the scenario at every save, with a note |
| `story_runs` | One row per run (the **run number**): scenario + version, language, status, start/end time, turns, actions, twist turn, ending, models used, LLM call count, error, replay-pool flag, times replayed, and the **checkpoint** (full story state after the last turn) with how often the run was continued |
| `story_events` | Every step of a run, in order: `director_narration`, `twist`, `rejected_dialogue`, `review`, `dialogue` (+ reasoning, decision), `action`, `world_state`, `conclusion_check`, `conclusion`, `error` |
| `llm_calls` | Every prompt and response (story agents and the scenario generator): agent, model, latency, success/error. Kept for `LLM_LOG_RETENTION_DAYS` (default 30) |

**How it behaves**
- Events are written **as they happen** through a background queue, so recording never slows the story down. If a run stops halfway, what happened so far is kept, with status `failed` or `aborted`. Runs cut off by a server restart are marked `aborted` on the next start.
- **Checkpoint after every turn:** the run's turns so far and its full story state (memories, world state, events) are saved after each turn. An unfinished run (`failed` / `aborted` / `incomplete` without an ending) can be **continued** from the player: the AI resumes the same run number from its last saved turn. When a story gets its ending the checkpoint is cleared, and the run can only be played again.
- **Every run can be watched again** from the player's **Purani stories** list, complete or not.
- A run is `completed` when it has an ending and no failed (`...`) turns. Only completed runs join the **replay pool**.
- **When the LLM is down:** before a story starts, the API makes one tiny LLM call. If it fails (invalid key, exhausted quota, outage), a completed run of the same scenario is **replayed as-is**, turn by turn (`REPLAY_TURN_DELAY` seconds apart). Same language first, least-replayed first.
- `GET /api/run/stream?mode=` `auto` (default: live, or replay if the LLM is down) · `live` (always generate) · `saved` (always replay).
- **Files stay in sync:** every save is also written to `scenarios/<id>/scenario.json` as a backup (and for git). Scenario files that aren't in the database yet, such as ones added through git, are imported on startup. The database is never overwritten by files.
- **If the database is unavailable,** the player keeps working from those JSON files (images fall back to initials), stories still run live but aren't recorded, and the admin panel is read-only. The app retries while Neon wakes up and reconnects later.
- Manual import: `uv run python -m src.import_data` · manual migration: `uv run alembic upgrade head`.

> Tip: run a few stories per scenario while your API key works, so the replay pool has something to fall back on.

---

## 8. LLM models & resilience

| Task | Model chain |
|---|---|
| **Running a story** (Director, characters, Reviewer) | `GEMINI_MODEL` (default `gemini-2.5-flash`) → `GEMINI_FALLBACK_MODELS` (`gemini-2.5-flash-lite`, `gemini-flash-latest`) → OpenAI `OPENAI_MODEL` *(only if `OPENAI_API_KEY` is set)* |
| **New with AI** | gpt-oss (`GPT_OSS_BASE_URL`) → `SCENARIO_GEMINI_MODEL` (`gemini-3.5-flash`) → `SCENARIO_GEMINI_FALLBACK_MODELS`. **Never OpenAI** |

- **Retries:** rate limits (429), overload (503), network / DNS errors and empty responses are retried with increasing waits before moving on.
- **Quota note:** Gemini's free tier limits requests **per model per day** (around 20 for `gemini-2.5-flash`), and one story uses 60+ calls. That's why the chain spans several models, and why the generator uses separate ones.
- **OpenAI is paid.** Leave `OPENAI_API_KEY` empty if you'd rather fall back to saved stories than pay.

---

## 9. The story engine in depth

### 9.1 Character memory
Each character keeps a rolling memory of 20 entries: what it said, what others said, twists, and actions done to it. The last 10 entries go into its prompt, along with its own last 5 lines and every action it has already performed, so it doesn't repeat itself.

### 9.2 Open-ended actions
Characters aren't limited to a menu. Any realistic physical action is allowed, and pattern matching turns it into world-state changes that later prompts can see:

| Action contains | World state |
|---|---|
| money / pay / give | `money_exchanged`, `money_from`, `money_to` |
| bribe / chai_pani | `bribe_offered`, `bribe_from`, `bribe_to` |
| challan / ticket / fine | `challan_written`, `challan_target` |
| key / confiscate / snatch | `keys_confiscated`, `keys_taken_from` |
| record / video / film | `being_recorded`, `recorder` |
| block / stand_in_front | `vehicle_blocked`, `vehicle_blocked_by` |
| show / display / hold_up | `{actor}_showed_something` |
| call / phone / dial | `{actor}_made_call` |
| chai / tea | `chai_offered` |
| sit / ground / collapse | `{actor}_on_ground` |
| push / shove / grab | `physical_confrontation_{actor}` |
| cry / wail / sob | `{actor}_crying` |
| whistle / blow | `whistle_blown` |
| *anything else* | `action_{type}_{actor}` |

Validation only checks that the action has a type, that its target (if any) is an existing character, and that the actor isn't targeting itself.

### 9.3 Reasoning layer
Every character turn is structured JSON, which forces the model to think before it speaks:
```json
{
  "reasoning": "What changed and what my strategy is this turn",
  "decision": "talk | act | both",
  "dialogue": "Spoken line, in character",
  "action": { "type": "Grab_Keys", "target": "Ahmed Malik", "description": "What exactly I physically do" }
}
```

### 9.4 Deep personas & anti-repetition
- Personas change tactics by turn band (1–3, 4–6, 7–9, 10+), so characters escalate instead of looping.
- **Appeal decay:** each character has appeal keywords (for example "mere bachche"). The engine counts how often each appeal has been used and tells the character the crowd is tiring of it: *Fresh → Used once → Tiring → Worn out*.
- **Three layers against repetition:** code (no speaker twice in a row, no two-character ping-pong for 4+ turns), context (previous lines and actions shown with "say something new"), and the Reviewer.

### 9.5 Director & twists
- A 4-phase arc: **Setup (1–4) → Escalation (5–9) → Complication (10–15) → Climax & resolution (16+)**.
- Narration must add at least one new sensory detail every turn.
- At `twist_turn` (default 9) the Director **invents a twist** from the story so far. It updates the world state and every character's memory.

### 9.6 Conclusion rules
A story can only end after `min_turns` turns and `min_actions` physical actions, at least `post_twist_turns` turns after the twist, and on alternating turns until close to the limit. At `max_turns` it is always closed with a Director-written ending (or the scenario's fallback ending). The Director's prompt also requires a real deal, a twist, and every character to have spoken.

### 9.7 Reviewer
A lifelong local of the scene's setting who checks four things: **language realism** (per-character notes from the scenario), **logical consistency** (realistic amounts and reactions), **repetition**, and **action logic**. Major issues trigger one regeneration with the suggestion. Minor issues are logged only.

---

## 10. Configuration reference

All settings live in `.env` (copy from `.env.example`). Restart the API after changing it.

| Variable | Default | Purpose |
|---|---|---|
| `GOOGLE_API_KEY` | — | Gemini key (stories, and generator fallback) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Main story model |
| `GEMINI_FALLBACK_MODELS` | `gemini-2.5-flash-lite,gemini-flash-latest` | Backup story models |
| `OPENAI_API_KEY` | *(empty)* | Optional paid last-resort for stories |
| `OPENAI_MODEL` | `gpt-5` | OpenAI model |
| `ADMIN_PASSWORD` | *(empty = admin disabled)* | Admin panel password |
| `DATABASE_URL` | *(empty = no database)* | Postgres URL (Neon: use the pooled connection string). Stores scenarios, images, versions and every run |
| `REPLAY_TURN_DELAY` | `2.5` | Seconds between turns when replaying a saved run |
| `LLM_LOG_ENABLED` | `true` | Store every LLM prompt and response |
| `LLM_LOG_RETENTION_DAYS` | `30` | Delete logged prompts older than this (checked at startup and daily) |
| `GPT_OSS_BASE_URL` | *(empty)* | Your gpt-oss server (OpenAI-compatible, e.g. `http://host:8000/v1`) |
| `GPT_OSS_MODEL` | `gpt-oss-120b` | gpt-oss model name |
| `GPT_OSS_API_KEY` | *(empty)* | gpt-oss server key, if it needs one |
| `GPT_OSS_REASONING_EFFORT` | `medium` | `low` / `medium` / `high` |
| `SCENARIO_GEMINI_MODEL` | `gemini-3.5-flash` | Generator's Gemini fallback |
| `SCENARIO_GEMINI_FALLBACK_MODELS` | `gemini-3.5-flash-lite,gemini-3.1-flash-lite` | More generator fallbacks |
| `GPT_OSS_MAX_TOKENS` / `GPT_OSS_TIMEOUT` / `SCENARIO_GEN_PARALLEL` | `12000` / `600` / `3` | Optional generator tuning |

Frontend: `frontend/.env` → `VITE_API_URL` (default `http://localhost:8080`).

**Per-scenario story settings** (admin → Settings):

| Setting | Default | Meaning |
|---|---|---|
| `max_turns` | 20 | Story is always closed at this turn |
| `min_turns` | 8 | No ending before this |
| `twist_turn` | 9 | When the Director injects a twist |
| `post_twist_turns` | 5 | Minimum turns after the twist |
| `min_actions` | 5 | Physical actions needed before an ending |
| `max_dialogue_length` | 250 | Length hint for each line |
| `temperature` | 0.85 | Creativity (0–2) |

---

## 11. Scenario file format

Scenarios live in the database; each one is also mirrored to `scenarios/<id>/scenario.json` (the format below, also used by Export / Import). Images saved in the database are referenced as `/api/images/<id>`.

```jsonc
{
  "id": "rickshaw_accident",
  "status": "published",                 // or "draft" (hidden from the player)
  "title": "The Rickshaw Accident",
  "subtitle": "Shahrah-e-Faisal, Karachi",
  "description": "The story seed every agent sees…",
  "setting": { "location": "…", "time": "…", "weather": "…", "crowd": "…" },
  "background_image": "/img12.png",
  "settings": { "max_turns": 20, "min_turns": 8, "twist_turn": 9, "…": "…" },
  "characters": [{
    "key": "saleem", "name": "Saleem", "label": "Saleem (Rickshaw Driver)",
    "description": "…", "goals": ["…"], "inventory": ["…"],
    "persona": "YOU ARE SALEEM — A DESPERATE RICKSHAW DRIVER. …",
    "english_style": "…",
    "appeals": { "Bachche/children appeal": ["bachche", "my kids", "…"] },
    "review_notes_urdu": "…", "review_notes_english": "…",
    "voice": { "voice": "hi-IN-MadhurNeural", "rate": "+15%", "pitch": "-4Hz" },
    "image": "/img4.png", "color": "amber"
  }],
  "prompts": {
    "character": "{persona}\n\n{context}\n…",
    "character_language_urdu": "…", "character_language_english": "…",
    "director_select_speaker": "…", "director_twist": "…", "director_conclusion": "…",
    "reviewer_urdu": "…", "reviewer_english": "…",
    "fallback_conclusion": "Plain-text ending used if the Director fails"
  }
}
```
Prompts are Python `str.format` templates: `{placeholder}` is filled by the engine, and literal braces are written `{{ }}`. The admin panel lists the allowed and required placeholders for each prompt.

Included scenarios: **The Rickshaw Accident** (default), **Khaali Degche Aur Hungama**, and the drafts **Empty Buffet** and **The Stuck Lift** (AI-generated).

---

## 12. API reference

**Public**
| Method | Path | Description |
|---|---|---|
| GET | `/api/scenarios` | Published scenarios |
| GET | `/api/scenarios/{id}` | Player view of a scenario (no prompts) |
| GET | `/api/images/{id}` | Image stored in the database |
| GET | `/api/scenarios/{id}/images/{file}` | Legacy image file from `scenarios/<id>/images/` |
| GET | `/api/run/stream?scenario=&lang=urdu\|english&mode=auto\|live\|saved` | Run a story as SSE: `meta`, `turns`, `conclusion`, `done`, `error` |
| POST | `/api/run?scenario=&lang=` | Run a full story and return it at once (also writes `story_output.json`, `prompts_log.json`) |
| GET | `/api/run/stream?continue_run=<run id>` | Continue an unfinished run from its last saved turn (sends the saved turns first, then new ones) |
| GET | `/api/runs?scenario=&continuable=true\|false&limit=&offset=` | Saved runs for the player (every run with at least one turn), newest first |
| GET | `/api/runs/{id}` | One saved run: turns + ending, to play again |
| GET | `/api/story` | Last story |
| GET | `/api/tts?text=&speaker=&scenario=` | MP3 speech in the character's voice |

**Admin** (header `Authorization: Bearer <token>`)
| Method | Path | Description |
|---|---|---|
| POST | `/api/admin/login` | `{password}` → `{token}` (valid 12 h) |
| GET | `/api/admin/meta` | Placeholders per prompt, voices, colours, default settings, database status |
| GET | `/api/admin/scenarios` | All scenarios including drafts |
| GET / PUT / DELETE | `/api/admin/scenarios/{id}` | Read / validate + save / delete |
| POST | `/api/admin/scenarios` | Create a copy: `{id, title, copy_from}` |
| POST | `/api/admin/scenarios/generate` | New with AI: `{brief, num_characters}` → SSE `progress`, `done`, `error` |
| POST | `/api/admin/scenarios/{id}/images` | Upload an image to the database: `{filename, data (base64)}` (PNG / JPG / WEBP, ≤ 5 MB) |
| GET | `/api/admin/scenarios/{id}/versions` | Version history |
| GET | `/api/admin/scenarios/{id}/versions/{v}` | One saved version |
| POST | `/api/admin/scenarios/{id}/versions/{v}/restore` | Restore a version (saved as a new version) |
| GET | `/api/admin/scenarios/{id}/export` | Download the scenario with embedded images |
| POST | `/api/admin/scenarios/import` | Import an export (or plain `scenario.json`) as a new scenario |
| GET | `/api/admin/runs?scenario=&status=&language=&limit=&offset=` | Recorded runs, newest first, with status counts |
| GET | `/api/admin/runs/{id}` | A run with every event in order |
| GET | `/api/admin/runs/{id}/llm-calls` | Every prompt/response of a run |
| PATCH | `/api/admin/runs/{id}` | `{in_replay_pool: true\|false}` |
| DELETE | `/api/admin/runs/{id}` | Delete a run with its events and prompts |

---

## 13. Project structure

```
├── src/
│   ├── api.py                  FastAPI: player, streaming, TTS, admin, replay fallback
│   ├── main.py                 Terminal runner (optional scenario id argument)
│   ├── config.py               StoryConfig (built from a scenario's settings)
│   ├── db.py                   Database connection + migrations on startup (async SQLAlchemy + asyncpg)
│   ├── models.py               Tables: scenarios, characters, prompts, images, versions, runs, events, llm_calls
│   ├── scenario_store.py       Scenarios in the database (+ JSON mirror, read-only fallback, versions, images, export/import)
│   ├── run_recorder.py         Records every run step by step; replay picking; admin run queries
│   ├── import_data.py          Imports scenario files + images and old saved stories into the database
│   ├── scenarios.py            Validation, placeholder rules, JSON file format
│   ├── scenario_generator.py   "New with AI": prompts, checks, gpt-oss → Gemini chain
│   ├── schemas.py              Pydantic models: StoryState, CharacterProfile, DialogueTurn
│   ├── story_state.py          Initial state, memories, goals, inventory
│   ├── actions.py              Open-ended action validation + world-state effects
│   ├── graph/narrative_graph.py   LangGraph loop, twist, anti-repetition, conclusion rules
│   ├── agents/
│   │   ├── base_agent.py       LLM chain + retries + logging
│   │   ├── character_agent.py  Structured reasoning / dialogue / action
│   │   ├── director_agent.py   Speaker choice, narration, twist, conclusion
│   │   └── reviewer_agent.py   Realism / logic / repetition gate
│   └── prompts/character_prompts.py   Builds character prompts from scenario templates
├── alembic/                    Database migrations (run automatically on API start)
├── scenarios/<id>/scenario.json (+ images/)   Backup/mirror of each scenario (source of truth: database)
├── frontend/                   React 19 + Vite + Tailwind 4 + Framer Motion
│   └── src/  App.jsx (player) · admin/AdminApp.jsx (scenario editor) · admin/RunsView.jsx (Stories) · lib/api.js
├── Dockerfile                  API container (port 7860, e.g. Hugging Face Spaces)
├── Technical_Report.md         Technical report (design and evaluation notes)
└── .env.example                All configuration options
```

---

## 14. Deployment

- **API:** `docker build -t narrative . && docker run -p 7860:7860 --env-file .env narrative`. The Dockerfile targets Hugging Face Spaces (port 7860).
- **Frontend:** `cd frontend && npm run build`, then serve `frontend/dist` from any static host. Set `VITE_API_URL` to your API URL before building.
- **Database:** use Neon or any Postgres through `DATABASE_URL`. Scenarios, admin edits, images, history and every run live there, so nothing is lost when a host with an ephemeral disk (such as Hugging Face Spaces) restarts. Migrations run automatically on start.
- Use a strong `ADMIN_PASSWORD` in production, and never commit `.env`.

---

## 15. Troubleshooting

| Symptom | Fix |
|---|---|
| `ERR_CONNECTION_REFUSED` / "Connection lost" in the browser | The API isn't running, or runs on another port. Start it, and make sure `frontend/.env` → `VITE_API_URL` matches the port. |
| `[Errno 98] Address already in use` | Another program uses the port (e.g. Docker on 8080). Use `--port 8081` and set `VITE_API_URL=http://localhost:8081`. |
| `429 RESOURCE_EXHAUSTED` | Gemini's daily free quota is used up for that model. Wait, add more fallback models, set up gpt-oss for the generator, or rely on saved stories. |
| `503 UNAVAILABLE … high demand` | Google's servers are overloaded, which is temporary. Retries and fallbacks handle most cases; otherwise try again in a few minutes. |
| Dialogue shows `...` | Every model in the chain failed for that turn (quota, overload, network). Such stories are never saved. |
| Admin login returns 503 | `ADMIN_PASSWORD` is not set in `.env`. Set it and restart the API. |
| Admin says "Not logged in" after a restart | The session expired or the password changed. Log in again. |
| `[DB] Could not connect` | Check `DATABASE_URL`. Neon can take a moment to wake up; the app retries and reconnects later. |
| Admin shows "read-only" / save returns 503 | The database isn't connected. Fix `DATABASE_URL` and restart the API. |
| A run stays "running" | It's still generating (the timeline updates live). Runs interrupted by a restart are marked `aborted` on the next start. |
| "The AI is unavailable … no saved story" | The LLM is down and nothing is saved for that scenario yet. Run a few stories while the key works. |
| Listen / voice doesn't play | Edge TTS needs internet access. |
| `ModuleNotFoundError: src` | Run commands from the repo root. |
