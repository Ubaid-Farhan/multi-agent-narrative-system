"""
"New with AI": turn a short scene idea into a complete scenario (story seed, setting, characters with
deep personas, appeals, reviewer notes, voices, and every Director / Reviewer / character prompt).

Quality comes from three things:
  1. The built-in Rickshaw scenario is shown to the model as the gold standard to match.
  2. Work is split into focused steps (blueprint -> one call per character -> one call per prompt)
     instead of one giant response.
  3. Every rewritten prompt is checked (placeholders, JSON braces) and sent back for fixing if broken.

Model: the self-hosted gpt-oss server (GPT_OSS_BASE_URL); Gemini only if that server is down. Never paid OpenAI.
Images are not generated — they are added from the admin panel.
"""
import asyncio
import copy
import json
import os
import re
from typing import AsyncIterator, Dict, List, Optional

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from . import scenarios as scn

load_dotenv()

GOLD_SCENARIO_ID = scn.DEFAULT_SCENARIO_ID
GOLD_PERSONA_EXAMPLES = ("Saleem", "Constable Raza")  # two contrasting characters shown as examples
MAX_PARALLEL_CALLS = int(os.getenv("SCENARIO_GEN_PARALLEL", "3"))
FIX_ATTEMPTS = 2

# Prompts rewritten for the new scene. character_language_english has nothing scene-specific.
ADAPTED_PROMPTS = [
    "character", "character_language_urdu", "director_select_speaker", "director_twist",
    "director_conclusion", "reviewer_urdu", "reviewer_english",
]

VOICE_GUIDE = """TTS voices (dialogue is Roman Urdu, which the hi-IN voices read best):
- hi-IN-MadhurNeural = male, hi-IN-SwaraNeural = female  ← use these for almost every character
- en-IN-PrabhatNeural = male, en-IN-NeerjaNeural = female ← only if a character speaks almost ONLY English
  (code-switching elites still use hi-IN; the dialogue is Roman Urdu)
Make characters sound distinct with rate (-25%..+30%) and pitch (-12Hz..+12Hz):
older/heavier/commanding → slower and lower; young/anxious/theatrical → faster and higher."""


# ─────────────────────────────── the craft brief shared by every call ───────────────────────────────

DESIGNER_SYSTEM = """You are a senior narrative designer for a multi-agent AI street-theatre engine.
Autonomous LLM agents play the characters; a Director agent picks who speaks and narrates the scene;
a Reviewer agent rejects unrealistic lines. A scene lasts ~20 turns, gets an AI-generated twist around
turn 9, and ends when a messy, earned compromise is reached. Your writing is the ONLY thing that makes
these agents feel like real people — generic output produces a generic, boring story.

What makes a scenario work (apply all of it):
1. ONE concrete, physical incident that has just happened and cannot be walked away from — something
   blocks everyone from simply leaving (a crowd, a locked gate, a blocked road, a family obligation).
2. Every character wants something DIFFERENT and has both LEVERAGE (what they can use) and a
   VULNERABILITY (what they fear). No neutral bystanders; even the mediator has a selfish motive.
3. A clear "currency of resolution" (money, an apology, a signature, keys, honour) so negotiations
   can go through offers and counter-offers before a deal.
4. Class, age, status and power differences create friction. Everyone argues from their own logic.
5. Hyper-specific, local, sensory detail: real place names, prices in rupees, brands, food, heat,
   sounds, smells, how people in that exact place talk. Never generic "a city street".
6. Each character has a comic FLAW that makes them sometimes funny without knowing it.
7. Characters do NOT know each other's names unless the story says so — they address each other by
   role ("BMW wala", "aunty", "beta", "sahab"). This is a hard rule the engine relies on.
8. Language: dialogue is Roman Urdu (Urdu in English letters) with realistic English mixing by class —
   working-class characters ~95% Urdu, educated/elite characters code-switch mid-sentence.
9. Tactics must EVOLVE across the scene (turns 1-3 / 4-6 / 7-9 / 10+) and never repeat the same move.
10. Everything must stay realistic and grounded — no magic, no violence beyond pushing/grabbing,
    nothing sexual, no real public figures, no hate toward any group.

Write in English (Roman Urdu only inside example lines), with the same density and specificity as the
gold examples you are shown. Match their length — do not shorten."""


def _gold() -> Dict:
    return scn.load_scenario(GOLD_SCENARIO_ID)


def _blueprint_example(gold: Dict) -> Dict:
    return {
        "title": gold["title"],
        "subtitle": gold.get("subtitle", ""),
        "description": gold["description"],
        "setting": gold.get("setting", {}),
        "dramatic_engine": {
            "core_conflict": "A poor rickshaw driver and a rich BMW owner collided; who pays, and how much?",
            "why_no_one_can_leave": "Both vehicles block the road, a crowd surrounds them, a constable arrives.",
            "currency_of_resolution": "Cash for the damage (realistic: 2,000-5,000 rupees) plus bribes.",
            "possible_complications": [
                "Ahmed's flight status changes", "Raza's senior is spotted nearby",
                "A video of the scene starts going viral", "The rickshaw damage turns out worse",
            ],
            "ending_shape": "Money changes hands, nobody is fully happy, traffic slowly resumes.",
        },
        "characters": [
            {k: c.get(k) for k in ("name", "label", "description", "goals", "inventory", "voice", "color")}
            | {"role": r, "gender": "male", "leverage": lev, "vulnerability": vul}
            for c, r, lev, vul in zip(gold["characters"], [
                "Rickshaw driver (the poor victim)", "Rich businessman (the privileged party)",
                "Corrupt traffic constable (the authority)", "Nosy shopkeeper (the self-appointed judge)",
            ], [
                "The crowd sympathises with the poor man", "Money and connections",
                "Can impound, write challans, take keys", "Claims to have seen everything; knows everyone",
            ], [
                "Cannot afford any payment; fears police", "Missing his flight; fears the hostile crowd",
                "Cameras and his DSP", "Being ignored or losing the spotlight",
            ])
        ],
        "fallback_conclusion": gold["prompts"]["fallback_conclusion"],
    }


# ─────────────────────────────── LLM plumbing ───────────────────────────────

def _build_llm():
    """
    gpt-oss (GPT_OSS_BASE_URL) first; Gemini only if that server is down. No paid OpenAI here.
    Gemini uses its own models (SCENARIO_GEMINI_MODEL...) so it doesn't eat the story models' daily quota.
    """
    chain, labels = [], []

    base_url = os.getenv("GPT_OSS_BASE_URL", "").strip()
    if base_url:
        chain.append(ChatOpenAI(
            model=os.getenv("GPT_OSS_MODEL", "gpt-oss-120b"),
            base_url=base_url,
            api_key=os.getenv("GPT_OSS_API_KEY") or "not-needed",
            temperature=0.8,
            max_tokens=int(os.getenv("GPT_OSS_MAX_TOKENS", "12000")),
            timeout=float(os.getenv("GPT_OSS_TIMEOUT", "600")),
            max_retries=1,
            reasoning_effort=os.getenv("GPT_OSS_REASONING_EFFORT", "medium"),
        ))
        labels.append("gpt-oss")

    if os.getenv("GOOGLE_API_KEY"):
        # Different models from the story chain (GEMINI_MODEL / GEMINI_FALLBACK_MODELS): Gemini quotas are per model.
        models = [os.getenv("SCENARIO_GEMINI_MODEL", "gemini-3.5-flash"),
                  *os.getenv("SCENARIO_GEMINI_FALLBACK_MODELS", "gemini-3.5-flash-lite,gemini-3.1-flash-lite").split(",")]
        for model in dict.fromkeys(m.strip() for m in models if m.strip()):
            chain.append(ChatGoogleGenerativeAI(model=model, temperature=0.8, max_output_tokens=16384, max_retries=1))
        labels.append("Gemini")

    if not chain:
        raise RuntimeError("No model configured for 'New with AI': set GPT_OSS_BASE_URL (gpt-oss server) "
                           "or GOOGLE_API_KEY (Gemini fallback).")
    llm = chain[0].with_fallbacks(chain[1:]) if len(chain) > 1 else chain[0]
    return llm, " → ".join(labels)


def _text(response) -> str:
    content = response.content
    if isinstance(content, list):
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return content or ""


async def _call(llm, sem: asyncio.Semaphore, user: str) -> str:
    """One model call (the fallback chain is tried inside); waits and retries on overload / rate limits."""
    transient = ("429", "503", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "overloaded", "high demand", "timed out",
                 "Timeout", "Cannot connect", "Connection", "name resolution")
    attempts = 4
    for attempt in range(attempts):
        try:
            async with sem:
                return _text(await llm.ainvoke([("system", DESIGNER_SYSTEM), ("human", user)]))
        except Exception as e:
            if attempt < attempts - 1 and any(t in str(e) for t in transient):
                await asyncio.sleep(15 * (attempt + 1))
                continue
            raise
    return ""


def friendly_error(e: Exception) -> str:
    """Readable message for the admin panel instead of a raw provider error."""
    text = str(e)
    if any(t in text for t in ("503", "UNAVAILABLE", "high demand", "overloaded")):
        return ("The AI models are overloaded right now (503). Please try again in a few minutes — "
                "or set GPT_OSS_BASE_URL in .env to use your own gpt-oss server.")
    if any(t in text for t in ("429", "RESOURCE_EXHAUSTED", "quota")):
        return ("The Gemini daily free quota is used up (429). Try again later, or set GPT_OSS_BASE_URL "
                "in .env to use your own gpt-oss server.")
    if any(t in text for t in ("API_KEY_INVALID", "API key not valid", "401", "PERMISSION_DENIED")):
        return "The API key was rejected. Check GOOGLE_API_KEY / GPT_OSS_API_KEY in .env and restart the API."
    return text or e.__class__.__name__


def _parse_json(text: str) -> Dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.S)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in the response")
    return json.loads(cleaned[start:end + 1])


async def _call_json(llm, sem, user: str, check=None) -> Dict:
    """Call, parse JSON, optionally validate; on failure send the error back and retry."""
    prompt, last_error = user, ""
    for _ in range(FIX_ATTEMPTS + 1):
        raw = await _call(llm, sem, prompt)
        try:
            data = _parse_json(raw)
            if check:
                check(data)
            return data
        except Exception as e:
            last_error = str(e)
            prompt = (f"{user}\n\n=== YOUR PREVIOUS ANSWER WAS REJECTED ===\nProblem: {last_error}\n"
                      "Return the complete corrected JSON object only.")
    raise ValueError(f"model output was invalid after retries: {last_error}")


# ─────────────────────────────── step 1: blueprint ───────────────────────────────

def _check_blueprint(num_characters: int):
    def check(data: Dict):
        for key in ("title", "subtitle", "description", "setting", "dramatic_engine", "characters", "fallback_conclusion"):
            if not data.get(key):
                raise ValueError(f"missing '{key}'")
        chars = data["characters"]
        if not isinstance(chars, list) or len(chars) != num_characters:
            raise ValueError(f"'characters' must be a list of exactly {num_characters}")
        names = [str(c.get("name", "")).strip() for c in chars]
        if any(not n for n in names) or len(set(names)) != len(names):
            raise ValueError("every character needs a unique, non-empty name")
        for c in chars:
            if len(c.get("goals") or []) < 3:
                raise ValueError(f"{c.get('name')}: give at least 3 goals")
        if len(data["description"].split()) < 90:
            raise ValueError("description is too short — write 120-180 words like the example")
    return check


def _blueprint_prompt(brief: str, num_characters: int, gold: Dict) -> str:
    return f"""Design a new scenario from this idea (it may be in Roman Urdu or English):

\"\"\"{brief.strip()}\"\"\"

Create exactly {num_characters} characters. If the idea names or implies characters, use them;
invent what is missing so the conflict is rich (the example has a victim, a privileged party,
an authority figure and a self-appointed mediator — use a similar spread of power where it fits).

=== GOLD STANDARD (match this depth, specificity and length) ===
{json.dumps(_blueprint_example(gold), indent=2, ensure_ascii=False)}

=== FIELD RULES ===
- title: 2-5 words, evocative. subtitle: the exact location, e.g. "Liberty Market, Lahore".
- description: 120-180 words, present tense, the moment right after the incident: who, what broke/happened,
  why nobody can leave, the crowd/onlookers, heat/sounds/smells, the authority approaching, the pressure.
  Use the characters' real names here (the narrator knows them).
- setting: object with location, time, weather, crowd, environment and one scene-specific object group
  (like "vehicles") — each value one vivid sentence.
- dramatic_engine: as in the example; 4-6 possible_complications grounded in THIS scene.
- characters[]: name (culturally fitting full name or "Title Name" like "Uncle Jameel"),
  label ("Name (Role)"), role, gender, description (70-110 words: situation, how they speak, what they
  physically might do, what they fear), goals (4, concrete and partly conflicting with others'),
  inventory (3-5 concrete items that could be USED in the scene), leverage, vulnerability,
  voice {{"voice","rate","pitch"}}, color (all different, one of: {", ".join(scn.CHARACTER_COLORS)}).
- fallback_conclusion: 2 sentences in Roman Urdu, the scene quietly returning to normal (used only if the
  Director fails to write an ending).

{VOICE_GUIDE}

Return ONE JSON object with exactly these keys: title, subtitle, description, setting, dramatic_engine,
characters, fallback_conclusion. No markdown, no commentary."""


# ─────────────────────────────── step 2: characters ───────────────────────────────

def _check_character(data: Dict):
    persona = data.get("persona", "")
    for header in ("PSYCHOLOGY", "LANGUAGE", "TACTICAL EVOLUTION", "FLAW", "HOW YOU ADDRESS OTHERS", "WOULD NEVER DO"):
        if header not in persona:
            raise ValueError(f"persona is missing the '{header}' section")
    if len(persona.split()) < 280:
        raise ValueError("persona is too short — match the examples (350-550 words)")
    appeals = data.get("appeals")
    if not isinstance(appeals, dict) or not 2 <= len(appeals) <= 4 or \
            not all(isinstance(v, list) and len(v) >= 4 for v in appeals.values()):
        raise ValueError("appeals must map 2-4 tactic names to lists of at least 4 keywords")
    for key in ("english_style", "review_notes_urdu", "review_notes_english"):
        if not str(data.get(key, "")).strip():
            raise ValueError(f"missing '{key}'")


def _character_prompt(blueprint: Dict, char: Dict, gold: Dict) -> str:
    examples = []
    for name in GOLD_PERSONA_EXAMPLES:
        g = scn.get_character(gold, name)
        if g:
            examples.append({k: g.get(k) for k in ("name", "persona", "english_style", "appeals",
                                                   "review_notes_urdu", "review_notes_english")})
    others = [f"- {c['name']} ({c.get('role', '')}): {c.get('description', '')}"
              for c in blueprint["characters"] if c["name"] != char["name"]]
    return f"""Write the full agent profile for ONE character of this scenario.

=== SCENARIO ===
Title: {blueprint['title']} — {blueprint['subtitle']}
{blueprint['description']}
Dramatic engine: {json.dumps(blueprint['dramatic_engine'], ensure_ascii=False)}

=== THIS CHARACTER ===
{json.dumps(char, indent=2, ensure_ascii=False)}

=== THE OTHER CHARACTERS (this character does NOT know their names) ===
{chr(10).join(others)}

=== GOLD EXAMPLES from another scenario (match structure, depth and length exactly) ===
{json.dumps(examples, indent=2, ensure_ascii=False)}

=== WHAT TO WRITE ===
persona — 350-550 words, second person, with these sections in this order (same headings as the examples):
  "YOU ARE <NAME IN CAPITALS> — <A SHORT PUNCHY ROLE LINE>."
  PSYCHOLOGY: age, circumstances, numbers (income/prices), what they really want and fear, why they are
    not stupid, what power they hold here.
  LANGUAGE: exact register and English-mixing level, verbal tics, 1-2 example lines in Roman Urdu.
  YOUR TACTICAL EVOLUTION: Turn 1-3 / Turn 4-6 / Turn 7-9 / Turn 10+ — a DIFFERENT strategy in each band.
  a situational-intelligence section (like "STREET INTELLIGENCE — crowd-reading") about reading the room
    and never repeating an appeal.
  YOUR FLAW — <label>: how they are unintentionally funny or self-defeating, with concrete examples.
  HOW YOU ADDRESS OTHERS (you don't know their names): one line per other character with 2-4 role-based
    forms of address, then "NEVER use anyone's actual name — you don't know them." (only exception: someone
    they genuinely know, stated explicitly).
  WHAT YOU WOULD NEVER DO: 4 bullets.
english_style — 3 lines like the examples: style description + 2 example lines in English.
appeals — 2-4 recurring emotional/tactical appeals this character is likely to overuse. Name each one in
  plain words like the examples ("Bachche/children appeal", "Flight urgency"), each mapped to
  6-12 short lowercase keywords (Roman Urdu spellings AND English) that detect it in dialogue.
review_notes_urdu — 1-2 sentences: what the Reviewer must check about this character's language and
  behaviour in Roman Urdu mode (register, English level, politeness, physicality).
review_notes_english — 1 sentence: the personality traits to check in English mode.

Return ONE JSON object with keys: persona, english_style, appeals, review_notes_urdu, review_notes_english."""


# ─────────────────────────────── step 3: prompts ───────────────────────────────

PROMPT_GUIDANCE = {
    "character": "Rewrite the GUIDELINES bullets for the new location, heat/sounds and forms of address; keep the rest.",
    "character_language_urdu": "Rewrite the per-character English-mixing rules and the 'Real ... example' lines for THESE characters.",
    "director_select_speaker": "Rewrite the story phases (who does what in each phase), the complication examples, and the environmental detail list for THIS scene. Keep the director rules and JSON format.",
    "director_twist": "Adapt the setting references and the examples of complications to THIS scene.",
    "director_conclusion": "Rewrite the conclusion conditions (what 'a deal' means here) and the per-character fate questions for THESE characters, and the final picture of THIS place.",
    "reviewer_urdu": "Make the reviewer a lifelong local of THIS place; adapt the realism checks (realistic amounts/behaviour for this scene). Keep {character_review_notes} on its own bullet under LANGUAGE REALISM.",
    "reviewer_english": "Adapt the setting and logical-consistency examples to THIS scene. Keep {character_review_notes} under CHARACTER PERSONALITY.",
}


def _fields(template: str) -> List[str]:
    return scn._template_fields(template)


def _check_template(name: str, original: str):
    spec = scn.PROMPT_PLACEHOLDERS[name]
    original_fields = set(_fields(original))

    def check(template: str):
        try:
            fields = set(_fields(template))
        except ValueError as e:
            raise ValueError(f"broken braces ({e}); literal braces must be written {{{{ and }}}}")
        unknown = fields - set(spec["allowed"])
        if unknown:
            raise ValueError(f"unknown placeholders {sorted(unknown)}; allowed: {spec['allowed']}")
        missing = original_fields - fields
        if missing:
            raise ValueError(f"placeholders removed: {sorted(missing)} — every placeholder of the original must stay")
        if "{{" in original and "{{" not in template:
            raise ValueError("the JSON response format block must keep its doubled braces {{ }}")
        if len(template) < 0.6 * len(original):
            raise ValueError("far shorter than the original — keep every section")
    return check


def _template_prompt(name: str, original: str, blueprint: Dict, characters: List[Dict]) -> str:
    cast = "\n".join(f"- {c['name']} ({c.get('role', '')}): {c.get('description', '')}" for c in characters)
    spec = scn.PROMPT_PLACEHOLDERS[name]
    return f"""Adapt one prompt template of the engine from the Rickshaw scenario to a NEW scenario.

=== NEW SCENARIO ===
Title: {blueprint['title']} — {blueprint['subtitle']}
{blueprint['description']}
Dramatic engine: {json.dumps(blueprint['dramatic_engine'], ensure_ascii=False)}
Characters:
{cast}

=== TEMPLATE "{name}" (currently written for the Rickshaw scenario) ===
<<<ORIGINAL
{original}
ORIGINAL>>>

=== HOW TO ADAPT ===
{PROMPT_GUIDANCE.get(name, "Replace every Rickshaw-specific detail with this scenario's equivalent.")}
- Replace EVERY reference to the old scene (Shahrah-e-Faisal, rickshaw, BMW, Saleem, Ahmed, Raza, Jameel,
  Karachi traffic, bumper prices...) with this scenario's own people, places and realistic numbers.
- Keep the same structure, headings, rules and roughly the same length. Do not add new sections.
- Placeholders in single braces like {{description}} are filled by the engine: keep EVERY one that the
  original uses, spelled exactly the same. Allowed: {", ".join("{" + p + "}" for p in spec["allowed"])}.
- Literal braces (the JSON example block) are written doubled: {{{{ and }}}}. Keep that block's keys unchanged.

Return ONLY the rewritten template between these two lines, nothing else:
<<<TEMPLATE
...
TEMPLATE>>>"""


async def _adapt_template(llm, sem, name: str, original: str, blueprint: Dict, characters: List[Dict]) -> tuple[str, Optional[str]]:
    """Returns (template, warning). Falls back to the original template if the model keeps breaking it."""
    check = _check_template(name, original)
    user = _template_prompt(name, original, blueprint, characters)
    prompt, last_error = user, ""
    for _ in range(FIX_ATTEMPTS + 1):
        raw = await _call(llm, sem, prompt)
        match = re.search(r"<<<TEMPLATE\s*\n(.*?)\n?\s*TEMPLATE>>>", raw, flags=re.S)
        template = (match.group(1) if match else raw).strip("\n")
        try:
            check(template)
            return template + ("\n" if original.endswith("\n") else ""), None
        except ValueError as e:
            last_error = str(e)
            prompt = (f"{user}\n\n=== YOUR PREVIOUS ANSWER WAS REJECTED ===\nProblem: {last_error}\n"
                      "Rewrite it again, fixing this, between <<<TEMPLATE and TEMPLATE>>>.")
    return original, f"Prompt '{name}' could not be adapted ({last_error}); kept the Rickshaw version — edit it in Prompts."


# ─────────────────────────────── orchestration ───────────────────────────────

def _event(kind: str, **data) -> Dict:
    return {"type": kind, **data}


async def generate_scenario(brief: str, num_characters: int = 4) -> AsyncIterator[Dict]:
    """Yields progress events; the last one is {'type': 'done', 'scenario': {...}, 'warnings': [...]}."""
    if not brief or len(brief.strip()) < 10:
        raise ValueError("Describe the scene in at least one sentence.")
    if not 2 <= num_characters <= 6:
        raise ValueError("Number of characters must be between 2 and 6.")

    llm, model_label = _build_llm()
    sem = asyncio.Semaphore(MAX_PARALLEL_CALLS)
    gold = _gold()
    warnings: List[str] = []

    yield _event("progress", step="blueprint", message=f"Designing the story and characters ({model_label})…")
    blueprint = await _call_json(llm, sem, _blueprint_prompt(brief, num_characters, gold),
                                 _check_blueprint(num_characters))
    names = [c["name"] for c in blueprint["characters"]]
    yield _event("progress", step="blueprint_done", message=f"“{blueprint['title']}” — {', '.join(names)}")

    # Step 2: characters (in parallel)
    yield _event("progress", step="characters", message="Writing deep personas…")
    char_tasks = {
        c["name"]: asyncio.create_task(_call_json(llm, sem, _character_prompt(blueprint, c, gold), _check_character))
        for c in blueprint["characters"]
    }
    details: Dict[str, Dict] = {}
    for coro in asyncio.as_completed(list(char_tasks.values())):
        await coro
        done = [n for n, t in char_tasks.items() if t.done() and not t.exception()]
        yield _event("progress", step="characters", message=f"Personas: {len(done)}/{len(names)} done")
    for name, task in char_tasks.items():
        details[name] = task.result()

    characters = []
    used_keys = set()
    for c in blueprint["characters"]:
        d = details[c["name"]]
        key = re.sub(r"[^a-z0-9]+", "_", c["name"].lower()).strip("_") or "character"
        while key in used_keys:
            key += "_2"
        used_keys.add(key)
        voice = c.get("voice") if isinstance(c.get("voice"), dict) else {}
        characters.append({
            "key": key,
            "name": c["name"],
            "label": c.get("label") or c["name"],
            "description": c.get("description", ""),
            "goals": [str(g) for g in c.get("goals", [])],
            "inventory": [str(i) for i in c.get("inventory", [])],
            "persona": d["persona"],
            "english_style": d["english_style"],
            "appeals": {str(k): [str(w).lower() for w in v] for k, v in d["appeals"].items()},
            "review_notes_urdu": d["review_notes_urdu"],
            "review_notes_english": d["review_notes_english"],
            "voice": {
                "voice": voice.get("voice") if voice.get("voice") in scn.TTS_VOICES else "hi-IN-MadhurNeural",
                "rate": voice.get("rate") or "+0%",
                "pitch": voice.get("pitch") or "+0Hz",
            },
            "image": "",
            "color": c.get("color") if c.get("color") in scn.CHARACTER_COLORS else scn.CHARACTER_COLORS[len(characters) % len(scn.CHARACTER_COLORS)],
        })

    # Step 3: prompts (in parallel)
    yield _event("progress", step="prompts", message="Adapting Director, Reviewer and character prompts…")
    prompts = copy.deepcopy(gold["prompts"])
    prompt_tasks = {
        name: asyncio.create_task(_adapt_template(llm, sem, name, gold["prompts"][name], blueprint, characters))
        for name in ADAPTED_PROMPTS
    }
    finished = 0
    for coro in asyncio.as_completed(list(prompt_tasks.values())):
        await coro
        finished += 1
        yield _event("progress", step="prompts", message=f"Prompts: {finished}/{len(ADAPTED_PROMPTS)} done")
    for name, task in prompt_tasks.items():
        template, warning = task.result()
        prompts[name] = template
        if warning:
            warnings.append(warning)
    prompts["fallback_conclusion"] = str(blueprint["fallback_conclusion"]).strip()

    scenario = {
        "title": str(blueprint["title"]).strip(),
        "subtitle": str(blueprint["subtitle"]).strip(),
        "description": str(blueprint["description"]).strip(),
        "setting": blueprint["setting"] if isinstance(blueprint["setting"], dict) else {"details": str(blueprint["setting"])},
        "background_image": "",
        "status": "draft",
        "generated_from": brief.strip(),
        "settings": copy.deepcopy(gold["settings"]),
        "characters": characters,
        "prompts": prompts,
    }
    scenario = scn.validate_scenario(scenario)
    yield _event("done", scenario=scenario, warnings=warnings)
