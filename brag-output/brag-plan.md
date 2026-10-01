# Brag plan — The Rickshaw Accident (Multi-Agent Narrative System)

**What it is:** A LangGraph story engine where AI agents act out a Karachi street fight: a rickshaw has hit a BMW, and nobody can leave until it's settled.
**Who it's for:** Hackfest x Datathon 2026 judges, GenAI builders, and anyone who has watched a Karachi roadside argument.
**What sets it apart:** Four characters with their own memory and tactics, a Director that invents a new twist mid-story, and a Reviewer agent that sends back any line that isn't realistic for Karachi.
**Most impressive / funniest claim:** The Reviewer rejects lines that aren't realistic ("Rickshaw bumper: 2,000–5,000, not 50,000").
**Visual hook:** The real scene art (rickshaw into BMW), a screen-shake impact, and horns.
**Real UI shown:** The player's dialogue bubble (a colored name header, typewriter text, an italic action line), the Director narration bar, the amber progress bar, and the "Start story" button.
**Tone:** `default` with a street-drama flavor: punchy, playful, amber/orange Karachi heat.
**Share caption:** A rickshaw hits a BMW in Karachi. Six AI agents have to sort it out.

## Angle
Pitch it as a street drama with an AI cast, not as an architecture diagram. The characters' real lines do the talking, and the agent structure comes through as plot beats: the Director's twist and the Reviewer's rejection.

## Visual identity
- Colors from the app: black / gray-950, amber-500 → orange-600 gradients, amber-300 headings, and the per-character gradients (Ahmed blue→indigo, Raza/Saleem slate, Jameel emerald→teal).
- System sans (the app's Tailwind default), bold and tight.
- Assets: `img12.png` (crash scene), `img5.png` (standoff), character cutouts `img8` (Saleem), `img3` (Ahmed), `img10` (Raza), `img9`/`img7` (Jameel).

## Storyboard (20.0s, 1920×1080, 30fps)
| # | Time | Scene | On screen | Sound |
|---|---|---|---|---|
| 1 Hook | 0.0–3.0 | Crash-scene art, fast push-in, impact shake at 0.35s | "A rickshaw just hit a BMW." (slams in, holds) + "Shahrah-e-Faisal, Karachi · 5:30 PM" | Horn blast + low impact, music kicks in on the hit |
| 2 Reveal | 3.0–6.2 | Four cutouts pop in one by one with name pills | "Four AI agents. One dent." | Soft pops on each entrance |
| 3 Show it | 6.2–10.6 | The app's dialogue UI: Ahmed's bubble types out "Dekhiye, this is absolutely ridiculous. Mujhe Dubai jaana hai!", then a cut to Raza: "Abe chabi de! Documents dikhao!" + action "Grab_Keys → Ahmed Malik"; Director bar and progress bar advance | Quiet typewriter ticks, whoosh on the cut |
| 4 Reviewer | 10.6–13.8 | A Reviewer agent card; a draft line gets stamped REJECTED | "Every line passes a Karachi reality check." / "Rickshaw bumper: Rs 2,000–5,000. Not 50,000." | Stamp thud |
| 5 Twist | 13.8–16.6 | "TURN 9" slams in, Director badge, twist text | "Then the Director throws a twist." / "Senior officer spotted approaching." | Riser into a drop |
| 6 Outro | 16.6–20.0 | Standoff art, title card, the "Start story" button gets clicked | "The Rickshaw Accident" / "A new story every run." / LangGraph · Gemini · Roman Urdu / English | Final chord + click |

Dialogue, action labels, the twist and the reviewer note all come from the repo (personas, README, Technical Report).
