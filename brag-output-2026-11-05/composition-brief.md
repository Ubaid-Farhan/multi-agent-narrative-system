# HyperFrames Composition Brief: AI Narrative Engine

## Objective
Create a 22-second launch-style marketing video for AI Narrative Engine using its real story art, portraits, and player layout.

## Output
- Composition directory: `../brag-output-2026-11-05/composition/`
- Rendered video: `../brag-output-2026-11-05/brag.mp4`
- Format: landscape — 1920x1080
- Duration: 22 seconds

## Source Material
- Project root: this repository (`AI Narrative /`)
- Primary files read: `README.md`, `frontend/src/App.jsx`, `frontend/src/admin/RunsView.jsx`, `frontend/src/lib/api.js`, `src/api.py`, `src/graph/narrative_graph.py`, `src/agents/director_agent.py`, `src/agents/reviewer_agent.py`, `scenarios/rickshaw_accident/scenario.json`
- Product name: AI Narrative Engine (README: Multi-Agent Narrative System)
- Tagline / strongest claim: “AI characters that argue, bargain, cry, bribe and improvise their way through a live street scene. Every run is a new story.”
- Key UI: dark full-screen player, character portrait and nameplate, dialogue panel, Director narration strip, scenario/language selector, saved story timeline.
- Copy that must appear verbatim:
  - “ONE CRASH. FOUR AGENDAS.”
  - “AI characters that argue, bargain, cry, bribe and improvise.”
  - “AI Narrative Engine”
- The illustrative Saleem dialogue is a sample line composed for this video, not a quote from a recorded run.

## Creative Direction
- Tone preset: default
- Creative direction: warm, cinematic Karachi street drama with a playful product-demo pace
- Interpretation: character-led, local, energetic but readable.
- Angle: one local collision becomes a four-way live story; show the player and its actual Director / Reviewer roles in motion.
- Hook: “ONE CRASH. FOUR AGENDAS.” over the real Karachi scene art and four portraits.
- Outro: “AI characters that argue, bargain, cry, bribe and improvise.” / AI Narrative Engine.
- Avoid: generic SaaS claims, abstract filler, performance metrics, fake testimonials, non-source UI claims, or unsourced dialogue presented as a real recorded quote.

## Visual Identity
- Background: #030303 / near-black player shell
- Text: #F9FAFB, muted slate secondary text
- Accent: #F59E0B amber; orange CTA gradient
- Display font: Inter 700/900, closest bundled family to the source's system sans
- Body font: Inter 400/700
- Visual references: `assets/images/karachi-scene.png`, `assets/images/roadside-scene.png`, and real character portraits Saleem, Ahmed Malik, Constable Raza and Uncle Jameel.
- LOOK: 1920x1080 landscape; #030303 ground, #F9FAFB ink, #F59E0B accent; Inter 900 headline / 700 UI / 400 body; 24px card corners, 2px amber focus edge, 15–25% amber atmosphere, 90% action-safe and 80% title-safe; grounded in illustrated Karachi street art and the actual dark player. Ban generic gradient wash, waveform, loose particles and looping title motion.

## Storyboard
Follow `brag-plan.md` as the creative contract: collision hook → scenario picker → live player/cast → Director and Reviewer event trace → recorded run/replay and title.

## Audio
- Role: warm, light music bed with restrained action accents.
- Music: `assets/music/happy-beats-business-moves-vol-9-by-ende-dot-app.mp3`
- Music treatment: 0.30 volume, 0.4-second fade-in, 1-second fade-out.
- Music cue guidance: preset at `../assets/music/cues/happy-beats-business-moves-vol-9-by-ende-dot-app.music-cues.json`, 114.84 BPM; cues at 4.23s, 10.54s and 12.65s. Optional timing only.
- Audio-reactive treatment: none.
- Audio-coupled moments: low-risk click at the scenario button; one soft impact on twist; low logo accent.
- SFX selection guidance: motion-matched and sparse, reduced under music.
- SFX analysis guidance: `/home/ubaid/.codex/plugins/cache/brag/brag/0.5.0/skills/brag/assets/sfx/sfx-analysis.md`.
- Planned SFX: `interface/click_003.ogg`, `impact/impactSoft_medium_001.ogg`, `impact/impactBell_heavy_000.ogg`.
- Audio files are copied into `composition/assets/`.

## HyperFrames Instructions
Use local assets and render locally. Every timed item has a stable id, `class="clip"`, `data-start` and `data-duration`; register one paused GSAP timeline. Keep the 22-second root duration and use seek-safe `fromTo` tweens. No voiceover. Run `npx hyperframes check` before preview and render. The Brag storyboard replaces the generic storyline and SPEC workflow.
