# Project Analysis — Multi-Agent Narrative System

*Analysis date: 2026-09-30 · Branch: `main` (commit `a138d55`)*

---

## 1. What the project is

An **AI storytelling engine**. You pick a scenario (for example *"a rickshaw hits a BMW on Shahrah-e-Faisal, Karachi"*), and a cast of LLM agents acts it out turn by turn. Each character has its own persona, goals, inventory and memory. The finished scene streams live to a React web player with a separate TTS voice for each character, in Roman Urdu or English.

It was built for **Hackfest x Datathon 2026 (Generative AI module)**; see `Technical_Report.md`. It has since grown into a small product with an admin panel, a Postgres database, recorded runs, resume-able stories and offline replay.

| Metric | Value |
|---|---|
| Tracked files | 92 |
| Backend (Python) | ~4,100 lines across 22 modules |
| Frontend (React) | ~2,400 lines (player + admin) |
| Bundled scenarios | 4 (`rickshaw_accident` default, `empty_buffet`, `khaali_degche_aur_hungama`, `the_stuck_lift`) |
| Commits | 15 |
| Automated tests | **None** |

---

## 2. Tech stack

| Layer | Technology |
|---|---|
| Agent orchestration | **LangGraph** `StateGraph` |
| LLMs | **Gemini** (`gemini-2.5-flash` primary + fallbacks) via `langchain-google-genai`; optional **OpenAI** fallback; self-hosted **gpt-oss** for scenario generation |
| API | **FastAPI** + Uvicorn, Server-Sent Events for streaming |
| Database | **Postgres** (Neon recommended), async SQLAlchemy 2 + asyncpg, **Alembic** migrations (run automatically at startup) |
| TTS | **edge-tts** (Microsoft Edge voices) |
| Frontend | **React 19**, **Vite 7**, **Tailwind CSS 4**, Framer Motion, lucide-react |
| Python tooling | **uv** (`pyproject.toml`), plus `requirements.txt` for Docker |
| Dev runner | `concurrently` (root `package.json`) |

---

## 3. Architecture

```
 scenario (DB or scenarios/<id>/scenario.json)
          │
          ▼
 ┌──────────────────────── NarrativeGraph (src/graph/narrative_graph.py) ────────────────────────┐
 │                                                                                               │
 │  director_select ──▶ character_respond ──▶ check_conclusion ──(continue)──▶ director_select    │
 │  (pick speaker,       (persona + memory +     (min turns / min actions /                        │
 │   narrate, twist       reasoning → JSON;       post-twist guard, then                           │
 │   at twist_turn)       Reviewer may reject     Director decides)                                │
 │                        → 1 retry; action              │ (conclude)                              │
 │                        validated → world state)       ▼                                         │
 │                                                    conclude ──▶ END                             │
 └───────────────────────────────────────────────────────────────────────────────────────────────┘
          │ each turn (SSE)                               │ every event + LLM call
          ▼                                               ▼
   React player (frontend/)                     RunRecorder → Postgres (story_runs, story_events, llm_calls)
```

### Agents (`src/agents/`)
| Agent | Role |
|---|---|
| `BaseAgent` | Shared LLM chain: Gemini → backup Gemini models → OpenAI. Classifies errors (quota, rate limit, overload, network, bad key) and puts a failing model on a **process-wide cooldown**. Salvages fields from JSON that was cut off. Raises `LLMUnavailableError` so a story stops cleanly. |
| `DirectorAgent` | Picks the next speaker, writes the narration, generates a context-aware **twist** at `twist_turn`, and decides when the story has ended. |
| `CharacterAgent` | Returns JSON (`reasoning`, `decision`, `dialogue`, `action`). Its context includes its goals, inventory, its last 10 memories, the last 15 lines of dialogue, its own earlier lines and actions (anti-repetition), and "appeal decay" (tactics the crowd is tired of). |
| `ReviewerAgent` | Checks each turn for realism, language register, logic and repetition. A rejection triggers **one** regeneration with the reviewer's feedback. |

### Key modules
| File | Purpose |
|---|---|
| `src/api.py` (812 lines) | Every HTTP endpoint: story run/stream/continue, TTS, the saved-run library, public scenarios, images, and the admin CRUD with token auth. |
| `src/run_recorder.py` | Records every run step by step, saves checkpoints for **Continue**, picks runs for replay, and cleans up LLM logs. |
| `src/scenario_store.py` | Scenario CRUD in the DB with a JSON-file mirror, version history, image storage, import/export. **Read-only when there is no DB.** |
| `src/scenario_generator.py` | "New with AI": turns a one-line brief into a blueprint, then characters, then prompt templates (gpt-oss first, Gemini as fallback). |
| `src/actions.py` | Free-form action validation and execution against the world state. |
| `src/models.py` | 8 tables: `scenarios`, `characters`, `prompts`, `images`, `scenario_versions`, `story_runs`, `story_events`, `llm_calls`. |
| `src/main.py` | Terminal-only runner (no web UI). |

### Story-shape controls (from each scenario's settings)
`max_turns` 20, `min_turns` 8, `twist_turn` 9, `min_actions` 5, `post_twist_turns` 5, `temperature` 0.85. The conclusion check has several hard blocks, so a story cannot end too early.

---

## 4. Strengths

1. **Clean agent design.** The graph is small and easy to read, and each agent has one job.
2. **Resilient LLM layer.** Error classification, per-model cooldowns, fallback chains and JSON salvage are handled more carefully than in most hackathon projects.
3. **Degrades gracefully.** Without a DB the app still runs (read-only scenarios). When the LLM is down, `mode=auto` replays a saved run.
4. **Observable.** Each run records the narration, rejected drafts, reviewer verdicts, actions, world-state snapshots and every raw prompt/response. This helps a lot with prompt tuning.
5. **Resumable runs.** Checkpoints let an unfinished story continue with the same memories and world state.
6. **Data-driven content.** Personas, prompts and settings live in the DB or JSON and are edited in the admin panel with versioning. Adding a scenario needs no code change.
7. **Reasonable basic security.** Admin tokens are HMAC-signed with an expiry and use `compare_digest`. Changing the password revokes all tokens. Scenario IDs are regex-checked, and the legacy image route guards against path traversal. Uploads are limited by type and size (5 MB).
8. **Thorough README.** It covers configuration, the API and troubleshooting.

---

## 5. Issues & risks (prioritised)

### High
| # | Issue | Where | Why it matters |
|---|---|---|---|
| H1 | **No automated tests** | whole repo | The conclusion rules, action validation, the error classifier (`_classify`) and `events_to_frontend_turns` are pure logic and easy to unit test. Right now any regression goes unnoticed. |
| H2 | **Public, unthrottled LLM and TTS endpoints** | `src/api.py:345`, `:386`, `:445` | Anyone who can reach the API can start unlimited story runs (each one makes about 40–60 LLM calls against your Gemini quota). They can also use `/api/tts` as a free TTS proxy with any length of `text`. CORS is `*`. That is fine locally, but risky if deployed. Add rate limiting, a `text` length cap and a concurrency limit on runs. |
| H3 | **Weak example admin password** | `.env.example` → `ADMIN_PASSWORD=12345` | If someone copies it without changing it, the admin panel (including delete) is protected only by `12345`. Leave the value blank in the example so admin stays disabled until a password is chosen. |

### Medium
| # | Issue | Where |
|---|---|---|
| M1 | **Global `last_story`** is shared by every user. With concurrent users, `/api/story` returns whoever finished last. | `src/api.py:49` |
| M2 | `POST /api/run` **writes `story_output.json` and `prompts_log.json` into the project root** on every call. These are leftovers from the CLI, and on a read-only container filesystem the write fails. | `src/api.py:411-440` |
| M3 | **`uv.lock` is git-ignored**, so `uv sync` resolves fresh versions on each machine. Only `requirements.txt` is pinned. Commit `uv.lock` for reproducible installs. | `.gitignore` |
| M4 | **Unused dependency** `langchain-groq` (never imported). | `pyproject.toml` |
| M5 | **Docker image serves only the API**, on port **7860** (Hugging Face Spaces style), while the frontend defaults to `http://localhost:8080`. The frontend must be built and hosted separately with `VITE_API_URL` set. | `Dockerfile`, `frontend/src/lib/api.js` |
| M6 | **Most features need `DATABASE_URL`**: admin edits, "New with AI" saves, run history, Continue and offline replay. Your local `.env` has `DATABASE_URL` **empty**, so these are currently off. | `.env` |
| M7 | `edge-tts` needs internet access to Microsoft's service. Voice fails offline or when it is blocked. | `src/api.py:352` |

### Low
- `api.py` (812 lines), `App.jsx` (911) and `AdminApp.jsx` (926) are large and would be easier to maintain split up (routers per area, player components).
- Turn events are printed to stdout with `print` rather than `logging`.
- The model cooldown table (`_cooldown_until`) is process-wide by design. With several Uvicorn workers, each worker keeps its own table.
- No CI pipeline, and no lint step on the Python side.

---

## 6. Your machine: current state

| Check | Status |
|---|---|
| Node.js | ✅ v24.21.0 installed |
| npm | ✅ installed |
| **Python 3.11+** | ❌ **not installed** (only the Microsoft Store stub) |
| **uv** | ❌ **not installed** |
| `node_modules` (root and `frontend/`) | ❌ not installed yet |
| `.env` | ✅ exists; `GOOGLE_API_KEY` and `ADMIN_PASSWORD` set; `DATABASE_URL` empty |

You don't need to install Python separately. `pyproject.toml` sets `python-preference = "managed"`, so **uv downloads the right Python by itself**.

---

## 7. How to run it (Windows / PowerShell)

### One-time setup
```powershell
# 1. Install uv (it also manages Python for you)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# → close and reopen the terminal so `uv` is on PATH

# 2. Install dependencies (run from the project folder)
cd "C:\Users\Rahat Ali Sheikh\Desktop\My-Work\multi-agent-narrative-system"
uv sync
npm install
cd frontend; npm install; cd ..
```

### Run (API + frontend together)
```powershell
npm run dev
```
| Service | URL |
|---|---|
| Story player | http://localhost:5173 |
| Admin panel | http://localhost:5173/admin |
| API | http://localhost:8080 (docs: http://localhost:8080/docs) |

### Other ways to run
```powershell
npm run dev:api                          # API only (port 8080)
npm run dev:frontend                     # frontend only
uv run python src/main.py                # terminal story, default scenario
uv run python src/main.py empty_buffet   # terminal story, another scenario
```

### Optional: unlock all features
Put a Postgres connection string (a free [Neon](https://neon.tech) database works) in `.env`:
```ini
DATABASE_URL=postgresql://user:pass@host/db?sslmode=require
```
When the API starts, Alembic creates the tables and the bundled `scenarios/*.json` files (with their images) are imported automatically. To re-import by hand, run `uv run python -m src.import_data`. It is safe to run more than once.

---

## 8. Recommended next steps

1. Add `pytest` with unit tests for `actions.py`, `_classify`, the conclusion rules and `events_to_frontend_turns`.
2. Add rate limiting (for example `slowapi`) and a length cap on `/api/tts` `text` before any public deployment.
3. Blank out `ADMIN_PASSWORD` in `.env.example`; commit `uv.lock`; remove `langchain-groq`.
4. Remove the `story_output.json` / `prompts_log.json` writes and the global `last_story` from the API path.
5. Add a GitHub Actions workflow that runs the tests, `ruff` and `npm run lint`.
