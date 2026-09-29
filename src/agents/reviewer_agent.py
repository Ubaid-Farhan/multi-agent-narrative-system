import json
from typing import Dict, Optional, Tuple
from .base_agent import BaseAgent
from ..config import StoryConfig
from ..schemas import StoryState
from ..scenarios import get_character


class ReviewerAgent(BaseAgent):
    """Reviews character outputs for realism, logical consistency, and repetition (prompts from the scenario)."""

    def __init__(self, config: StoryConfig):
        super().__init__("Reviewer", config)
        self.last_review: Dict = {}  # verdict of the last review (saved with the run)

    async def review_turn(self, character_name: str, dialogue: str,
                          action: Optional[Dict], state: StoryState) -> Tuple[bool, str]:
        """
        Review a character's dialogue and action.

        Returns:
            (approved: bool, feedback: str)
            If not approved, feedback contains the suggestion for regeneration.
        """
        self.last_review = {}
        profile = state.character_profiles.get(character_name)
        character_description = profile.description if profile else "Unknown"

        # Format action text
        if action and isinstance(action, dict) and action.get("type"):
            action_text = f"{action.get('type')}" + \
                         (f" → {action.get('target')}" if action.get('target') else "") + \
                         f": {action.get('description', 'no description')}"
        else:
            action_text = "No physical action this turn."

        # Get previous lines for repetition check
        previous_lines = [
            f"Turn {t.turn_number}: {t.dialogue[:120]}"
            for t in state.dialogue_history if t.speaker == character_name
        ]
        if previous_lines:
            prev_text = "\n".join(f"- {l}" for l in previous_lines[-5:])
        else:
            prev_text = "No previous lines (first time speaking)."

        # Format world state
        world_lines = []
        for key, value in state.world_state.items():
            if not key.startswith("_"):
                world_lines.append(f"- {key.replace('_', ' ').title()}: {value}")
        world_state = "\n".join(world_lines) if world_lines else "Nothing notable."

        is_english = getattr(self.config, 'language', 'urdu') == 'english'
        prompts = self.config.scenario["prompts"]
        prompt_template = prompts["reviewer_english"] if is_english else prompts["reviewer_urdu"]
        char = get_character(self.config.scenario, character_name)
        review_notes = char.get("review_notes_english" if is_english else "review_notes_urdu") or \
            "Does this sound like a real person in this situation?"

        prompt = prompt_template.format(
            character_name=character_name,
            character_description=character_description,
            character_review_notes=review_notes,
            dialogue=dialogue,
            action_text=action_text,
            previous_lines=prev_text,
            world_state=world_state
        )

        response = await self.generate_response(prompt)

        try:
            cleaned = self._clean_json_response(response)
            data = json.loads(cleaned)

            approved = data.get("approved", True)
            issues = data.get("issues", [])
            severity = data.get("severity", "none")
            suggestion = data.get("suggestion", "")
            self.last_review = {"approved": bool(approved), "severity": severity, "issues": issues,
                                "suggestion": suggestion, "rejected": (not approved and severity == "major")}

            if not approved and severity == "major":
                feedback = f"REJECTED: {'; '.join(issues)}. Suggestion: {suggestion}"
                print(f"  [Reviewer] {feedback}")
                return False, suggestion or "Try a completely different approach."

            if issues and severity == "minor":
                print(f"  [Reviewer] Minor issues: {'; '.join(issues)}")

            return True, ""

        except Exception as e:
            # If reviewer fails to parse, approve by default (don't block the story)
            print(f"  [Reviewer] Parse error: {e} — approving by default")
            self.last_review = {"approved": True, "rejected": False, "parse_error": str(e),
                                "note": "Reviewer output could not be read — approved by default"}
            return True, ""
