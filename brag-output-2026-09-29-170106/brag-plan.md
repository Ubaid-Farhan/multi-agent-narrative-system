# Brag plan v3: full explainer (Multi-Agent Narrative System)

Goal (from the user): a first-time evaluator should understand the whole idea **and** how it works. That needs a longer (~68s), chaptered explainer. It keeps the v2 opening the user liked.

**What it is:** Describe a scene. AI characters with their own psychology, memory and goals argue, bargain, bribe and improvise through it live. A Director runs the arc, a Reviewer rejects lines that aren't realistic, and every run is a new story.

## Storyboard (68.0s, 1920×1080, 30fps, 120 BPM grid from 0.35s)
| # | Time | Chapter | On screen |
|---|---|---|---|
| Hook | 0.0–3.4 | — | New with AI dialog, the brief types in, Generate clicked. "Write one sentence." |
| Title | 3.4–8.4 | — | "Multi-Agent Narrative System" + README tagline |
| 01 | 8.4–16.0 | The setup | The Rickshaw Accident scenario + 4 character cards with their real goals |
| 02 | 16.0–23.0 | How a turn works | 5-node loop: Director → Character agent → Reviewer → Memory + world state → Conclusion check → next turn |
| 03 | 23.0–31.0 | Inside one turn | Raza's bubble + the structured JSON (reasoning / decision / dialogue / action), world-state keys, the shared memory line |
| 04 | 31.0–36.5 | Quality control | Reviewer card with the REJECTED stamp + appeal decay Fresh → Used once → Crowd tiring → Worn out |
| 05 | 36.5–41.4 | The Director's arc | 4-phase bar, the turn marker, TWIST at turn 9, ending-earned rules |
| 06 | 41.4–46.4 | Watch it live | Player start screen → live turn with a voice waveform |
| 07 | 46.4–53.4 | New with AI | "Remember that sentence?" → progress log → Empty Buffet cast |
| 08 | 53.4–57.4 | Admin panel | Characters tab (Saleem's persona, voice), Save → "Saved. The next story run uses these changes." |
| 09 | 57.4–61.4 | Always on | Gemini chain fails → saved story replays from Neon Postgres |
| Outro | 61.4–68.0 | — | Title, tagline, tech stack, Start story click |

All copy comes from the repo (README, scenario.json, AdminApp.jsx, scenario_generator.py, narrative_graph.py, actions.py). The one exception is the agent's `reasoning` text in chapter 03, which is marked "example".
