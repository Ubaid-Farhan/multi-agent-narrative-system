from dataclasses import dataclass
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
    
