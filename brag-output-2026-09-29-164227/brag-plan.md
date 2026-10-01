# Brag plan v2 — Multi-Agent Narrative System (the whole platform)

**What it is:** Describe any street or social scene in one sentence. An AI writes the cast, and a team of LLM agents acts it out live, turn by turn.
**Who it's for:** GenAI builders, hackathon judges, and storytellers who want Pakistani street drama that sounds real.
**What sets it apart:** "New with AI" writes the full scenario (personas, voices, every prompt). A Director runs the arc and invents twists. A Reviewer rejects lines that aren't realistic. Saved stories replay when the LLM quota runs out.
**Most impressive claim:** One line of Roman Urdu becomes a complete, playable scenario with four deep personas.
**Visual hook:** The real brief typing into the New with AI dialog, then a whole cast popping out of it.
**Real UI shown:** The New with AI dialog and its real progress messages; the generated Empty Buffet cast in the player's coloured-initials fallback; the player's start screen (scenario picker, Roman Urdu / English, Start story); a live turn with the Listen voice; the Director bar.
**Tone:** `default` (punchy, playful, amber/orange).
**Share caption:** One sentence in, a whole AI cast out, arguing live in Roman Urdu.

## Real material used
- Brief: "Lahore ki shaadi mein khana waqt se pehle khatam ho gaya…" (the example brief in `AdminApp.jsx`)
- Generated result: "Empty Buffet": Chaudhry Tariq Iqbal (Groom's Father), Naeem Butt (Caterer), Shagufta Sultana (Bride's Phuppo), Hamza Khalid (Wedding Photographer), with their real colours
- Progress lines from `scenario_generator.py`; model label "gpt-oss → Gemini"
- Player scenarios: The Rickshaw Accident, Khaali Degche Aur Hungama
- Raza line + Grab_Keys, twist "Senior officer spotted approaching", reviewer note, the model chain gemini-2.5-flash → flash-lite → flash-latest → saved story

## Storyboard (24.0s, 1920×1080, 30fps, 120 BPM grid from 0.35s)
| # | Time | Scene | On screen |
|---|---|---|---|
| 1 Hook | 0.0–3.4 | The New with AI dialog, brief types in, Generate is clicked | "Write one sentence." |
| 2 Generate | 3.4–7.4 | Progress lines tick in → the dialog clears → four coloured-initial characters pop in | "It writes the whole cast." / "Personas, goals, voices and every prompt." |
| 3 Play | 7.4–12.0 | Player start screen: scenario picker + Roman Urdu, Start story clicked → live turn: Raza "Abe chabi de! Documents dikhao!", Grab_Keys, Listen waveform | "Streams live, with a voice for every character" |
| 4 Agents | 12.0–15.0 | "A Director runs the scene." / "A Reviewer throws out fake lines." + reviewer card with REJECTED stamp | |
| 5 Twist | 15.0–17.4 | TURN 9 slam, twist text | "Then the Director throws a twist." |
| 6 Resilience | 17.4–20.4 | Model chain fails one by one → the saved story replays from Postgres | "Quota gone? The show goes on." |
| 7 Outro | 20.4–24.0 | Title, tagline, feature chips, Start story click | "Multi-Agent Narrative System" / "Every run is a new story." |
