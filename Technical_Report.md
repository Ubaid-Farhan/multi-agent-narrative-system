# Technical Report: GenAI_DSS Multi-Agent Narrative System

**Hackfest x Datathon 2026 — Generative AI Module**

---

## 1. Abstract

This report describes the design and implementation of a **6-Agent Narrative System** that orchestrates four autonomous character agents, a Director agent, and a Reviewer agent through a conflict-driven street scene story set in Karachi. Built on **LangGraph**, the system goes significantly beyond the three mandatory components (Memory, Actions, Reasoning) by introducing **8 novel extensions** not required by the problem statement: deep psychological character personas with turn-by-turn tactical evolution, an open-ended action system using pattern-matching, LLM-generated context-aware story twists unique to every run, a dedicated Reviewer Agent that validates Karachi realism per turn, a 3-layer anti-repetition system, a multi-mechanism conclusion resistance system, a 4-phase story structure, and a real-time React frontend with SSE streaming. The system produces coherent 15-22 turn narratives with natural action frequency, dynamic twists, and authentic Karachi street language.

---

## 2. System Architecture

### 2.1 High-Level Design

The system follows a Director-Agent architecture orchestrated by a LangGraph `StateGraph`:

- **Director Agent**: Controls narrative pacing, selects speakers, narrates the scene, generates context-aware twists, and evaluates conclusion conditions.
- **4 Character Agents**: Each powered by a deep psychological persona. Autonomously generates dialogue and open-ended actions based on personality, memory, goals, and tactical evolution stage.
- **Reviewer Agent** *(Novel — not required)*: Acts as a "born-and-raised Karachiite" quality gate. Validates every character turn for language realism, logical consistency, repetition, and action logic. Rejects major issues with one retry.
- **FastAPI + React Frontend** *(Novel — not required)*: Real-time SSE streaming delivers each turn to the browser as it's generated.

```
                    ┌─────────────────┐
                    │   Entry Point   │
                    │  main.py / API  │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  NarrativeGraph  │
                    │  (StateGraph)    │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
    ┌─────────▼───┐  ┌──────▼──────┐  ┌───▼──────────┐
    │  Director    │  │  Character  │  │   Check      │
    │  Select +    │──│  Respond    │──│  Conclusion  │
    │  Narrate +   │  │  + Reviewer │  │  (5 checks)  │
    │  Twist @9    │  │  Check      │  └──────┬───────┘
    └─────────────┘  └─────────────┘         │
                                    continue ─┤── conclude → END
```

### 2.2 State Management

All state flows through a Pydantic `StoryState` model with 10 fields:

| Field | Type | Purpose |
|---|---|---|
| `seed_story` | `Dict` | Original scenario description and setting details |
| `current_turn` | `int` | Turn counter |
| `dialogue_history` | `List[DialogueTurn]` | Full dialogue transcript |
| `events` | `List[Dict]` | Chronological events (dialogue, narration, action) |
| `character_profiles` | `Dict[str, CharacterProfile]` | Name, description, goals, inventory per character |
| `character_memories` | `Dict[str, List[str]]` | Per-character memory buffers (sliding window of 20) |
| `world_state` | `Dict[str, Any]` | Mutable world facts updated by actions and twists |
| `is_concluded` | `bool` | Whether story has ended |
| `conclusion_reason` | `str` | Final narration explaining the ending |
| `story_narration` | `List[str]` | Director narration history |

### 2.3 LLM Configuration

| Parameter | Value | Rationale |
|---|---|---|
| Model | `gemma-3-27b-it` | Free-tier Google Generative AI; strong instruction following |
| Temperature | `0.75` | Tuned for creative, varied output while maintaining coherence |
| Max Output Tokens | `2000` | Sufficient for structured JSON with dialogue + action |
| Max Context | `4000` | Optimized for persona + context + memory + dialogue history |

---

## 3. Mandatory Component Implementations

### 3.1 Character Memory System

**Design**: Sliding window per-character memory with cross-character propagation.

Each character maintains up to 20 memory entries. After each turn:

1. **Speaker's memory** receives: `"Turn X: I said: {dialogue}"`
2. **All other characters' memories** receive: `"Turn X: {Speaker} said: {dialogue}"`
3. **Action memory**: When any action executes, ALL characters receive the action description
4. **Twist memory**: When a story twist fires, ALL characters receive the twist context

**Cross-character propagation** ensures that when Saleem grabs Ahmed's keys, Ahmed's memory records it and he reacts accordingly. In a physical street scene, everyone can see and hear everything — our memory system reflects this.

```python
# Memory update after each turn (narrative_graph.py)
speaker_mem.append(f"Turn {turn}: I said: {dialogue[:150]}")
for other in characters:
    other_mem.append(f"Turn {turn}: {speaker} said: {dialogue[:150]}")
```

### 3.2 Action System

**Design**: Open-ended actions with pattern-matching for intelligent world-state tracking.

Characters can perform **any realistic physical action** — the system doesn't restrict them to a fixed menu. The character prompt says: *"You can do ANYTHING a real person would do on a Karachi street — grab something, push someone, sit down, make a phone call, throw money, tear up a document, point at damage..."*

The system uses **13 pattern categories** to intelligently map free-form actions to world-state updates:

| Pattern | World State Effect |
|---|---|
| money/pay/give | `money_exchanged`, `money_from`, `money_to` |
| bribe/chai_pani | `bribe_offered`, `bribe_from`, `bribe_to` |
| challan/ticket/fine | `challan_written`, `challan_target` |
| key/confiscate/snatch | `keys_confiscated`, `keys_taken_from` |
| record/video/film | `being_recorded`, `recorder` |
| block/stand_in_front | `vehicle_blocked`, `vehicle_blocked_by` |
| push/shove/grab | `physical_confrontation_{actor}` |
| show/display/hold_up | `{actor}_showed_something` |
| call/phone/dial | `{actor}_made_call` |
| sit/ground/collapse | `{actor}_on_ground` |
| cry/wail/sob | `{actor}_crying` |
| whistle/blow | `whistle_blown` |
| *(any other)* | `action_{type}_{actor}` — catch-all ensures no action is lost |

This approach provides unlimited creative expressiveness while maintaining meaningful world-state tracking for other agents to react to.

### 3.3 Reasoning Layer

**Design**: Structured JSON output with explicit chain-of-thought reasoning powered by deep psychological personas.

Each character agent outputs:

```json
{
    "reasoning": "Internal thought — strategy, what changed, what's new",
    "decision": "talk | act | both",
    "dialogue": "Spoken words in character voice",
    "action": {
        "type": "Free-form label (e.g., Grab_Keys, Throw_Money)",
        "target": "character name or null",
        "description": "Vivid description of the physical action"
    }
}
```

The `reasoning` field forces chain-of-thought: the model must articulate its strategy before generating dialogue, improving decision quality. The `decision` field ensures an explicit choice between talking, acting, or both.

---

## 4. Novel Extensions Beyond Requirements

The following features go **beyond** what the problem statement requires. They demonstrate originality, design thinking, and deep understanding of multi-agent narrative challenges.

### 4.1 Deep Psychological Personas with Tactical Evolution *(Novel)*

Each character has a multi-paragraph psychological profile covering:

- **PSYCHOLOGY**: Deep background — age, income, fears, social strategies, street-smarts
- **LANGUAGE**: Specific rules tied to education level and social class
- **TACTICAL EVOLUTION**: How behavior changes across turn ranges — characters naturally evolve from shock to anger to strategy to negotiation
- **HARD CONSTRAINTS**: "WHAT YOU WOULD NEVER DO" — behavioral limits the LLM respects

Example: Saleem's evolution — Turn 1-3: SHOCKED/DESPERATE (begs, pleads) → Turn 4-6: ANGRY (blames Ahmed, challenges) → Turn 7-9: STRATEGIC (uses crowd, class divide, moral arguments) → Turn 10+: NEGOTIATING or ESCALATING (demands, not requests).

This produces stories where characters naturally change tactics across turns, creating dramatic arcs without any code-level forcing.

### 4.2 LLM-Generated Context-Aware Story Twists *(Novel)*

At turn 9, the **Director agent generates a unique story twist** via a dedicated LLM call. The twist is based on everything that has happened in the specific run — dialogue, actions, world state, character positions. Each run produces a **completely different twist** because it emerges from context.

The twist must: be realistic for Karachi, change the dynamic for at least 2 characters, and be impossible to ignore. Examples from actual runs: "dhaba gas cylinder explosion", "senior officer approaching", "live stream going viral."

**Post-twist breathing room**: 5 turns after the twist before conclusion is allowed, ensuring characters have time to react and adapt.

### 4.3 Reviewer Agent — Quality Gate *(Novel)*

A **6th agent** (not required by the problem statement) that runs after every character turn. Acts as a "born-and-raised Karachiite" who checks:

1. **Language realism**: Is Saleem (rickshaw driver) speaking too much English? Is Raza (cop) being too polite? Is Ahmed (businessman) not code-switching?
2. **Logical consistency**: Are monetary amounts realistic? (Rickshaw bumper: 2,000-5,000 PKR, not 50,000). Would a man earning 800/day refuse 20,000?
3. **Repetition**: Same emotional appeal used again? Same argument with different words?
4. **Action logic**: Does the physical action fit the current moment?

If rejected (major severity), the character gets **one retry** with the reviewer's feedback in context — creating a feedback loop that measurably improves output quality. All reviewer decisions are logged in `prompts_log.json` for full audit transparency.

### 4.4 3-Layer Anti-Repetition System *(Novel)*

| Layer | Mechanism | What It Prevents |
|---|---|---|
| **Code-level** | `max_consecutive = 1`, anti-ping-pong (4-turn detection) | Same speaker twice, 2 characters dominating |
| **Context-level** | Characters see their previous lines + actions with "say something COMPLETELY DIFFERENT" | Same dialogue points, same action types |
| **Agent-level** | Reviewer checks for semantic repetition | Same argument with different words, same emotional appeal |

### 4.5 5-Mechanism Conclusion Resistance *(Novel)*

| Mechanism | What It Does |
|---|---|
| `min_turns = 15` | Hard block before turn 15 |
| `min_actions = 5` | Hard block before 5 actions |
| Post-twist buffer | 5 turns after twist before conclusion possible |
| Even-turn gating | Before turn 18, only check on even turns |
| `max_turns = 25` | Hard cap forces conclusion as safety net |

This produces stories that feel complete — they don't end abruptly after 5 turns, and they don't drag on indefinitely.

### 4.6 4-Phase Story Structure *(Novel)*

The Director follows explicit narrative phases:
- **Phase 1 — Setup (Turns 1-4)**: Characters arrive, assess, take positions
- **Phase 2 — Escalation (Turns 5-9)**: Tensions rise, actions increase, crowd takes sides
- **Phase 3 — Complication (Turns 10-15)**: Twist fires, characters adapt, new dynamics
- **Phase 4 — Resolution (Turns 16-22)**: Final negotiations, deal struck, everyone compromises

This creates stories with natural narrative arcs rather than flat linear exchanges.

### 4.7 Real-Time Frontend with SSE Streaming *(Novel)*

A full narrative run takes 2-5 minutes. Rather than making users wait, the system **streams each turn in real-time**:

- **FastAPI backend** (`src/api.py`): `GET /api/run/stream` uses Server-Sent Events
- **React frontend**: `EventSource` receives turns as they're generated; auto-advances when new turn arrives; Next button disabled while waiting for next turn
- **Additional endpoints**: `POST /api/run` (full run), `GET /api/story` (retrieve last story)

### 4.8 Per-Character Language Modeling *(Novel)*

Language rules are deeply tied to each character's education level and social class:

| Character | Background | Language Pattern |
|---|---|---|
| **Saleem** | 5th class education, rickshaw driver | 95% Roman Urdu, only basic English words (please, sir, police) |
| **Ahmed Malik** | Textile export businessman | English-Urdu code-switching ("Dekhiye, this is absolutely ridiculous") |
| **Constable Raza** | 15-year traffic veteran | 90% blunt street Urdu ("Abe chabi de! Documents dikhao!") |
| **Uncle Jameel** | 30-year shopkeeper | 95% dramatic theatrical Urdu with TV English words |

---

## 5. Design Decisions

### 5.1 Code-Level vs. Prompt-Level Enforcement

We enforce **structural constraints** in code and **creative decisions** in prompts:

| Constraint | Enforcement | Rationale |
|---|---|---|
| No consecutive same speaker | Code (hard block) | LLM-reliable; ensures variety |
| Minimum story length | Code (min_turns = 15) | Guarantees complete narrative arc |
| Minimum actions | Code (action_count < 5) | Meets rubric requirement reliably |
| Twist injection timing | Code (turn 9 trigger) | Precise narrative pacing control |
| Anti-ping-pong | Code (4-turn detection) | Ensures all characters participate |
| Action content | Prompt (persona-driven) | Character psychology drives creative choices |
| Dialogue content | Prompt (deep persona) | Tactical evolution produces natural variety |
| Twist content | Prompt (LLM-generated) | Context-aware twists are more fitting |

### 5.2 Open-Ended Actions

We chose open-ended actions with pattern-matching over a fixed menu because: (1) unlimited creative expressiveness — characters naturally do things like "tear up the challan" or "wave down a taxi" that wouldn't be in any predefined list, (2) pattern-matching still captures meaningful world-state updates, and (3) the catch-all ensures no action is ever silently lost.

### 5.3 Reviewer Agent as Separate Agent

The reviewer is a separate agent (not part of the character prompt) because: (1) single responsibility — each agent does one thing well, (2) the reviewer can use a harsher "Karachiite street critic" persona without polluting the character's own voice, (3) the retry mechanism creates a feedback loop that improves quality, and (4) all reviewer decisions are independently logged for audit.

---

## 6. Evaluation Results

### 6.1 System Output Metrics

| Metric | Value |
|---|---|
| Turns per run | 15-22 (varies naturally within min/max bounds) |
| Actions per run | 5-9 (natural frequency, not forced) |
| Story twists | Unique LLM-generated twist every run |
| All 4 characters participate | Yes (anti-repetition + anti-ping-pong ensures this) |
| Language compliance | Saleem/Raza/Jameel speak Roman Urdu; Ahmed code-switches |
| Conclusion type | Negotiated settlement with specific amounts |
| Reviewer catches per run | 2-4 rejections with successful retries |

### 6.2 Rubric Compliance

| Rubric Component | Our Implementation | Key Strengths |
|---|---|---|
| **Working System (25)** | Runs via `uv run python src/main.py` or `npm run dev`. Clean, modular code. | 6 agents, LangGraph, Pydantic state, full logging |
| **JSON Compliance (15)** | `story_output.json` (events, conclusion, metadata), `prompts_log.json` (all agent calls) | Complete, meaningful, consistent with narrative flow |
| **Feature Implementation (15)** | All 3 mandatory + 8 novel extensions | Reviewer Agent, LLM twists, deep personas, SSE streaming, etc. |
| **Documentation (20)** | README (setup/usage/architecture), Technical Report (design decisions), PDF via pandoc/LaTeX | Clear justification for every design choice; see §7–8 for limitations and improvements |
| **Story Quality (10)** | Coherent narratives with dramatic arcs, realistic Karachi language | Reviewer ensures quality floor; personas ensure variety. Some repetition and theatrical tone remain (see §8). |

**Critical reflection:** Self-scores above are our own assessment. Independent evaluation may find runnability issues (e.g. missing `GOOGLE_API_KEY`), residual repetition in dialogue, or action rejections (e.g. `target: null`). We would improve by adding a runnability checklist, more reviewer retries or stricter prompts, and a fixed action target validator (§9).

### 6.3 Iterative Development

| Iteration | Key Change | Impact |
|---|---|---|
| Base → Memory | Characters remember past events | Coherent references to earlier turns |
| + Actions | Physical actions change world state | Story becomes more than dialogue |
| + Reasoning | Structured JSON with chain-of-thought | Better decision quality |
| + Anti-repetition | 3-layer system | No more stuck loops |
| + Story phases | 4-phase Director structure | Natural narrative arc |
| + Twists | LLM-generated complications | Unpredictable, engaging stories |
| + Personas | Deep psychological profiles | Varied, realistic character behavior |
| + Reviewer | Quality gate per turn | Language/logic/repetition caught |
| + Frontend | React + SSE streaming | Real-time visualization |

---

## 7. Limitations and Known Issues

We acknowledge the following limitations so that evaluators and future work can address them:

| Area | Limitation | Impact |
|------|------------|--------|
| **Actions** | Actions with `target: null` (e.g. *Wave_Down_Passerby → null*) are rejected by the validator. The LLM sometimes outputs null for “crowd” or “passerby” targets. | Some intended actions do not execute; world state may miss minor beats. |
| **Repetition** | Despite the 3-layer anti-repetition system and Reviewer, thematic repetition can occur (e.g. “bachchon ka kya,” “Inspector Farooq,” class contrast). Reviewer catches explicit repeats but not all semantic overlap. | Dialogue may feel repetitive in long runs. |
| **Dialogue tone** | Reviewer sometimes flags “theatrical” or “drama-serial” tone; retries improve but do not always remove it. | Occasional lines may sound scripted rather than spontaneous. |
| **Conclusion** | Conclusions often follow a similar pattern (money exchanged, parties disperse). Director has freedom but LLM tends toward negotiated settlement. | Endings can feel formulaic across runs. |
| **Runnability** | System requires `GOOGLE_API_KEY` in `.env`, `uv`, and Node.js. First-time runs can fail if any step is skipped. | Evaluators must follow README exactly; we provide troubleshooting in README. |
| **Report format** | This report is provided in Markdown. Problem statement requests PDF (LaTeX). We provide build instructions for PDF generation (§README). | PDF can be generated via pandoc or the provided LaTeX source. |

---

## 8. Future Improvements

If we had more time, we would prioritize:

1. **Runnability:** A single script or `make run` that checks for `.env`, prompts for API key if missing, and runs backend + frontend with clear first-time instructions.
2. **Action target handling:** Allow abstract targets (e.g. “crowd,” “passerby”) or map them to a synthetic world-state key so that actions are not rejected for null target.
3. **Stronger anti-repetition:** Semantic similarity check (e.g. embedding-based) in addition to Reviewer’s text-level feedback; or a “repetition budget” per character per theme.
4. **Conclusion diversity:** Director prompt or sampling strategy to encourage different conclusion types (e.g. police intervention, walkaway, crowd resolution) and avoid default “money handover” endings.
5. **Technical Report PDF:** Ship a pre-generated `Technical_Report.pdf` in the repository in addition to Markdown and LaTeX source, so judges need not run pandoc/LaTeX.

---

## 9. Summary of Features Beyond Requirements

The problem statement requires: Memory, Actions, Reasoning, max 25 turns, 5+ actions, story_output.json, prompts_log.json, README, Technical Report.

**Our system adds 8 features not required by the problem statement:**

| # | Feature | What It Does | Why It Matters |
|---|---|---|---|
| 1 | **Reviewer Agent** | 6th agent validates every turn for Karachi realism | Catches unrealistic language, illogical amounts, repetition |
| 2 | **Deep Psychological Personas** | Multi-paragraph character psychology with tactical evolution | Characters naturally evolve across turns, creating dramatic arcs |
| 3 | **LLM-Generated Twists** | Director creates unique context-aware twist each run | Every run is different; twists fit the specific story |
| 4 | **Open-Ended Actions** | Pattern-matching on free-form actions (13 categories + catch-all) | Unlimited creative expressiveness |
| 5 | **3-Layer Anti-Repetition** | Code + context + reviewer prevents repetition at 3 levels | No stuck dialogue loops or repeated actions |
| 6 | **5-Mechanism Conclusion Resistance** | min_turns, min_actions, post-twist buffer, gating, max_turns | Stories feel complete and earned |
| 7 | **4-Phase Story Structure** | Director follows Setup → Escalation → Complication → Resolution | Natural narrative pacing |
| 8 | **Real-Time Frontend + SSE** | React app streams turns live via Server-Sent Events | Interactive visualization of story generation |

---

## Appendix A: Technical Report PDF

The problem statement requests a **PDF (LaTeX)** technical report. This document is provided as:

- **Technical_Report.md** — Markdown source (this file).
- **Technical_Report.tex** — LaTeX source for compilation to PDF (see repo root).
- **Generating PDF:** From repo root, run either:
  - `pandoc Technical_Report.md -o Technical_Report.pdf` (requires [pandoc](https://pandoc.org/)), or
  - `pdflatex Technical_Report.tex` (requires a LaTeX distribution).

A pre-built PDF may be included in the submission bundle for evaluator convenience.

---

## Appendix B: File Structure

```
GenAi_DSS/
├── src/
│   ├── main.py                    # CLI entry point
│   ├── api.py                     # FastAPI server (POST/GET/SSE streaming)
│   ├── config.py                  # StoryConfig dataclass
│   ├── schemas.py                 # Pydantic models (StoryState, DialogueTurn, Action, CharacterProfile)
│   ├── actions.py                 # Open-ended action validation + pattern-based execution
│   ├── story_state.py             # StoryStateManager (initializes characters, memory, goals)
│   ├── agents/
│   │   ├── base_agent.py          # BaseAgent with LLM integration + prompt/response logging
│   │   ├── character_agent.py     # CharacterAgent (structured JSON reasoning + dialogue + action)
│   │   ├── director_agent.py      # DirectorAgent (speaker selection + twist generation + conclusion)
│   │   └── reviewer_agent.py      # ReviewerAgent (Karachi realism + consistency check per turn)
│   ├── prompts/
│   │   ├── character_prompts.py   # Deep psychological personas with tactical evolution
│   │   └── director_prompts.py    # Director prompts: speaker selection, twist generation, conclusion
│   └── graph/
│       └── narrative_graph.py     # LangGraph StateGraph + twist injection + reviewer integration
├── examples/
│   └── rickshaw_accident/
│       ├── seed_story.json        # Story seed with detailed setting (vehicles, location, weather)
│       └── character_configs.json # 4 character profiles with goals + inventory
├── Hackthon_Frontend_IBA/
│   └── frontend/                  # React + Vite frontend (SSE streaming, turn-by-turn display)
├── story_output.json              # Generated narrative trace (events, conclusion, metadata)
├── prompts_log.json               # LLM interaction audit log (all 6 agents)
├── package.json                   # Root scripts: dev, dev:frontend, dev:api
└── README.md                      # Setup, usage, architecture, features documentation
```
