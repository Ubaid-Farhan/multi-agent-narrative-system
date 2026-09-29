from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass
class StoryConfig:
    """Configuration for the story simulation."""
    model_name: str = "gpt-5"
    temperature: float = 0.85

    max_turns: int = 20
    min_turns: int = 8
    max_tokens_per_prompt: int = 3000
    max_context_length: int = 4000

    max_consecutive_same_character: int = 1

    num_characters: int = 4
    max_dialogue_length: int = 250
    language: str = "urdu"  # "urdu" = Roman Urdu, "english" = English
    
