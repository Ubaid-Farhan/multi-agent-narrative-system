from dataclasses import dataclass, field
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass
class StoryConfig:
    """Configuration for the story simulation."""
    # Primary LLM: Gemini. Fallback: OpenAI (used only if OPENAI_API_KEY is set).
    model_name: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    fallback_model_name: str = os.getenv("OPENAI_MODEL", "gpt-5")
    # Backup Gemini models tried when the primary is overloaded (503) or rate limited (429).
    gemini_fallback_models: tuple = tuple(
        m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-2.5-flash-lite,gemini-flash-latest").split(",") if m.strip()
    )
    temperature: float = 0.85

    max_turns: int = 20
    min_turns: int = 8
    max_tokens_per_prompt: int = 3000
    max_context_length: int = 4000

    max_consecutive_same_character: int = 1

    num_characters: int = 4
    max_dialogue_length: int = 250
    language: str = "urdu"  # "urdu" = Roman Urdu, "english" = English

    # Story-shape settings (overridden per scenario from the admin panel)
    twist_turn: int = 9
    min_actions: int = 5
    post_twist_turns: int = 5

    # Full scenario dict: characters, personas, prompts (see src/scenarios.py)
    scenario: dict = field(default_factory=dict)

    # RunRecorder (src/run_recorder.py) that saves every event / LLM call of this run; None = not recorded
    recorder: object = None

    @classmethod
    def from_scenario(cls, scenario: dict, language: str = "urdu") -> "StoryConfig":
        s = scenario.get("settings", {})
        return cls(
            language=language,
            scenario=scenario,
            num_characters=len(scenario.get("characters", [])),
            **{k: s[k] for k in ("max_turns", "min_turns", "temperature", "max_dialogue_length",
                                 "twist_turn", "min_actions", "post_twist_turns") if k in s},
        )
    
