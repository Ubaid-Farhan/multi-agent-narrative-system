import json
from typing import List, Dict, Optional, Tuple
from .base_agent import BaseAgent
from ..config import StoryConfig
from ..schemas import StoryState, CharacterProfile
from ..prompts.character_prompts import get_character_prompt


class CharacterAgent(BaseAgent):
    def __init__(self, name: str, config: StoryConfig):
        super().__init__(name, config)
        self.last_meta: Dict = {}  # reasoning / decision of the last response (saved with the run)

    async def respond(self, story_state: StoryState, context: str,
                      world_state_text: str = "") -> Tuple[str, Optional[Dict]]:
        """
        Generate a structured response: dialogue + optional action.

        Returns:
            (dialogue: str, action: dict or None)
            action dict has keys: type, target, description
        """
        character_profile = story_state.character_profiles.get(self.name)
        self.last_meta = {}

        prompt = get_character_prompt(
            character_name=self.name,
            character_profile=character_profile,
            context=context,
            config=self.config,
            world_state_text=world_state_text
        )

        # LLMUnavailableError is not caught here: the story stops cleanly if no model can answer.
        content = (await self.generate_response(prompt)).strip()

        try:
            # Try to parse structured JSON response
            cleaned = self._clean_json_response(content)
            data = json.loads(cleaned)

            dialogue = data.get("dialogue") or ""
            action = data.get("action")
            decision = data.get("decision", "talk")
            self.last_meta = {"reasoning": data.get("reasoning"), "decision": decision, "parsed": True}

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
            # Usually a cut-off answer: recover the dialogue from the partial JSON instead of showing raw JSON
            salvaged = self._salvage_fields(content, ["dialogue", "reasoning", "decision"])
            print(f"Warning: {self.name} response was not valid JSON ({e}); "
                  f"{'recovered the dialogue' if salvaged.get('dialogue') else 'no dialogue recovered'}.")
            self.last_meta = {"parsed": False, "parse_error": str(e), "salvaged": bool(salvaged.get("dialogue")),
                              "reasoning": salvaged.get("reasoning"), "decision": salvaged.get("decision")}
            if salvaged.get("dialogue"):
                return salvaged["dialogue"], None
            looks_like_json = content.lstrip().startswith(("{", "```", "[")) or '"dialogue"' in content
            return (content if content and not looks_like_json else "..."), None
