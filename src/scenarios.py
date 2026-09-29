"""
Scenario storage: every story (seed, characters, personas, prompts, settings) lives in
scenarios/<id>/scenario.json so it can be edited from the admin panel instead of code.
"""
import copy
import json
import re
import string
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).parent.parent
SCENARIOS_DIR = PROJECT_ROOT / "scenarios"
DEFAULT_SCENARIO_ID = "rickshaw_accident"

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

DEFAULT_SETTINGS = {
    "max_turns": 20,
    "min_turns": 8,
    "temperature": 0.85,
    "max_dialogue_length": 250,
    "twist_turn": 9,
    "min_actions": 5,
    "post_twist_turns": 5,
}

# Placeholders each prompt may use ("allowed"), and the ones it cannot work without ("required").
PROMPT_PLACEHOLDERS = {
    "character": {
        "allowed": ["persona", "context", "world_state_text", "language_rule", "english_final",
                    "character_name", "max_dialogue_length"],
        "required": ["persona", "context"],
    },
    "character_language_urdu": {"allowed": ["character_name"], "required": []},
    "character_language_english": {"allowed": ["character_name", "english_style"], "required": []},
    "director_select_speaker": {
        "allowed": ["description", "world_state_text", "recent_dialogue", "character_descriptions",
                    "current_turn", "max_turns", "action_count", "max_consecutive"],
        "required": ["character_descriptions"],
    },
    "director_twist": {
        "allowed": ["story_summary", "world_state_text", "character_descriptions", "current_turn"],
        "required": ["story_summary"],
    },
    "director_conclusion": {
        "allowed": ["story_summary", "world_state_text", "character_descriptions", "current_turn",
                    "max_turns", "action_count"],
        "required": ["story_summary"],
    },
    "reviewer_urdu": {
        "allowed": ["character_name", "character_description", "character_review_notes", "dialogue",
                    "action_text", "previous_lines", "world_state"],
        "required": ["dialogue"],
    },
    "reviewer_english": {
        "allowed": ["character_name", "character_description", "character_review_notes", "dialogue",
                    "action_text", "previous_lines", "world_state"],
        "required": ["dialogue"],
    },
    "fallback_conclusion": {"allowed": [], "required": []},
}


class ScenarioError(ValueError):
    """Raised for invalid scenario data or ids."""


def _check_id(scenario_id: str) -> str:
    if not isinstance(scenario_id, str) or not _ID_RE.match(scenario_id):
        raise ScenarioError("Scenario id must be lowercase letters, numbers, '-' or '_' (max 64 chars).")
    return scenario_id


def scenario_dir(scenario_id: str) -> Path:
    return SCENARIOS_DIR / _check_id(scenario_id)


def list_scenarios() -> List[Dict]:
    items = []
    if SCENARIOS_DIR.exists():
        for path in sorted(SCENARIOS_DIR.glob("*/scenario.json")):
            try:
                data = json.loads(path.read_text())
                items.append({"id": path.parent.name, "title": data.get("title", path.parent.name)})
            except (OSError, json.JSONDecodeError):
                continue
    return items


def load_scenario(scenario_id: str = DEFAULT_SCENARIO_ID) -> Dict:
    path = scenario_dir(scenario_id) / "scenario.json"
    if not path.exists():
        raise FileNotFoundError(f"Scenario '{scenario_id}' not found")
    data = json.loads(path.read_text())
    data["id"] = scenario_id
    data["settings"] = {**DEFAULT_SETTINGS, **data.get("settings", {})}
    return data


def _template_fields(template: str) -> List[str]:
    """Placeholder names used in a str.format template. Raises ValueError on broken braces."""
    return [field for _, field, _, _ in string.Formatter().parse(template) if field is not None]


def validate_scenario(data: Dict) -> Dict:
    """Validate and normalise scenario data. Raises ScenarioError with a readable message."""
    if not isinstance(data, dict):
        raise ScenarioError("Scenario must be a JSON object.")
    data = copy.deepcopy(data)

    if not str(data.get("title", "")).strip():
        raise ScenarioError("Title is required.")
    if not str(data.get("description", "")).strip():
        raise ScenarioError("Story description is required.")

    settings = {**DEFAULT_SETTINGS, **(data.get("settings") or {})}
    for key in ("max_turns", "min_turns", "max_dialogue_length", "twist_turn", "min_actions", "post_twist_turns"):
        try:
            settings[key] = int(settings[key])
        except (TypeError, ValueError):
            raise ScenarioError(f"Setting '{key}' must be a whole number.")
        if settings[key] < 0:
            raise ScenarioError(f"Setting '{key}' cannot be negative.")
    try:
        settings["temperature"] = float(settings["temperature"])
    except (TypeError, ValueError):
        raise ScenarioError("Setting 'temperature' must be a number.")
    if not 0 <= settings["temperature"] <= 2:
        raise ScenarioError("Temperature must be between 0 and 2.")
    if settings["min_turns"] > settings["max_turns"]:
        raise ScenarioError("min_turns cannot be greater than max_turns.")
    data["settings"] = settings

    characters = data.get("characters") or []
    if len(characters) < 2:
        raise ScenarioError("A scenario needs at least 2 characters.")
    names, keys = set(), set()
    for i, char in enumerate(characters):
        name = str(char.get("name", "")).strip()
        if not name:
            raise ScenarioError(f"Character #{i + 1} needs a name.")
        if name in names:
            raise ScenarioError(f"Duplicate character name '{name}'.")
        names.add(name)
        key = str(char.get("key") or re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_"))
        if key in keys:
            raise ScenarioError(f"Duplicate character key '{key}'.")
        keys.add(key)
        char["name"] = name
        char["key"] = key
        char.setdefault("label", name)
        char.setdefault("description", "")
        char["goals"] = [g for g in (char.get("goals") or []) if str(g).strip()]
        char["inventory"] = [g for g in (char.get("inventory") or []) if str(g).strip()]
        char.setdefault("persona", "")
        char.setdefault("english_style", "")
        char.setdefault("review_notes_urdu", "")
        char.setdefault("review_notes_english", "")
        appeals = char.get("appeals") or {}
        if not isinstance(appeals, dict) or not all(isinstance(v, list) for v in appeals.values()):
            raise ScenarioError(f"Appeals for '{name}' must map a name to a list of keywords.")
        char["appeals"] = appeals
        char.setdefault("voice", {"voice": "hi-IN-MadhurNeural", "rate": "+0%", "pitch": "+0Hz"})
        char.setdefault("image", "")
        char.setdefault("color", "slate")
    data["characters"] = characters

    prompts = data.get("prompts") or {}
    for prompt_name, spec in PROMPT_PLACEHOLDERS.items():
        template = prompts.get(prompt_name)
        if not isinstance(template, str) or not template.strip():
            raise ScenarioError(f"Prompt '{prompt_name}' is required.")
        if prompt_name == "fallback_conclusion":
            continue  # plain text, never formatted
        try:
            fields = _template_fields(template)
        except ValueError as e:
            raise ScenarioError(
                f"Prompt '{prompt_name}' has broken braces ({e}). Use {{{{ and }}}} for literal JSON braces.")
        unknown = sorted({f for f in fields if f not in spec["allowed"]})
        if unknown:
            raise ScenarioError(
                f"Prompt '{prompt_name}' uses unknown placeholder(s): {', '.join('{' + u + '}' for u in unknown)}.")
        missing = [f for f in spec["required"] if f not in fields]
        if missing:
            raise ScenarioError(
                f"Prompt '{prompt_name}' must contain: {', '.join('{' + m + '}' for m in missing)}.")
    data["prompts"] = prompts
    return data


def save_scenario(scenario_id: str, data: Dict) -> Dict:
    data = validate_scenario(data)
    data["id"] = scenario_id
    folder = scenario_dir(scenario_id)
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / "scenario.json.tmp"
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(folder / "scenario.json")
    return data


def get_character(scenario: Dict, name: str) -> Dict:
    for char in scenario.get("characters", []):
        if char.get("name") == name:
            return char
    return {}


def public_view(scenario: Dict) -> Dict:
    """What the story player needs: no prompts."""
    return {
        "id": scenario["id"],
        "title": scenario.get("title"),
        "subtitle": scenario.get("subtitle", ""),
        "description": scenario.get("description", ""),
        "background_image": scenario.get("background_image", ""),
        "characters": [
            {k: c.get(k) for k in ("key", "name", "label", "image", "color")}
            for c in scenario.get("characters", [])
        ],
    }
