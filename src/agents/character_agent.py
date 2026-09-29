import json
from typing import List, Dict, Optional, Tuple
from .base_agent import BaseAgent
from ..config import StoryConfig
from ..schemas import StoryState, CharacterProfile
from ..prompts.character_prompts import get_character_prompt


class CharacterAgent(BaseAgent):
    def __init__(self, name: str, config: StoryConfig):
        super().__init__(name, config)

    async def respond(self, story_state: StoryState, context: str,
                      world_state_text: str = "") -> Tuple[str, Optional[Dict]]:
        """
        Generate a structured response: dialogue + optional action.

        Returns:
            (dialogue: str, action: dict or None)
            action dict has keys: type, target, description
        """
        character_profile = story_state.character_profiles.get(self.name)

        prompt = get_character_prompt(
            character_name=self.name,
            character_profile=character_profile,
            context=context,
            config=self.config,
            world_state_text=world_state_text
        )

        try:
            content = await self.generate_response(prompt)
            content = content.strip()

            # Try to parse structured JSON response
            cleaned = self._clean_json_response(content)
            data = json.loads(cleaned)

            dialogue = data.get("dialogue") or ""
            action = data.get("action")
            decision = data.get("decision", "talk")

            # Validate action structure if present
            if action and isinstance(action, dict):
                if not action.get("type"):
                    action = None
            else:
                action = None

            # If decision is "act" but no dialogue, provide a minimal narration
            if decision == "act" and not dialogue and action:
                dialogue = f"*{action.get('description', 'does something')}*"

            # If we got no dialogue at all, fallback
            if not dialogue:
                dialogue = "..."

            return dialogue, action

        except (json.JSONDecodeError, Exception) as e:
            # Fallback: treat the whole response as dialogue (no action)
            print(f"Warning: {self.name} response was not valid JSON, treating as dialogue. Error: {e}")
            # Try to extract useful text from the response
            fallback_text = content if content else "..."
            # Strip any partial JSON artifacts
            if fallback_text.startswith("{"):
                fallback_text = "..."
            return fallback_text, None
