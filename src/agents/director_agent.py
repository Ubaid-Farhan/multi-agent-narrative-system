import json
from typing import List, Tuple, Optional, Dict
from .base_agent import BaseAgent
from ..config import StoryConfig
from ..schemas import StoryState
from ..actions import get_action_count


class DirectorAgent(BaseAgent):
    def __init__(self, config: StoryConfig):
        super().__init__("Director", config)
        self.last_selection: Dict = {}   # who the model asked for vs. who was chosen (saved with the run)
        self.last_conclusion_check: Dict = {}
        self.prompts = config.scenario["prompts"]

    def _format_world_state(self, state: StoryState) -> str:
        """Format world_state for prompt."""
        if not state.world_state:
            return "Nothing notable yet."
        lines = []
        for key, value in state.world_state.items():
            if key.startswith("_"):
                continue
            readable_key = key.replace("_", " ").title()
            lines.append(f"- {readable_key}: {value}")
        return "\n".join(lines) if lines else "Nothing notable yet."

    def _build_character_descriptions(self, state: StoryState,
                                       names: List[str] = None) -> str:
        """Build formatted character descriptions with goals."""
        char_lines = []
        profiles = state.character_profiles
        for name in (names or profiles.keys()):
            profile = profiles.get(name)
            if profile:
                goals_str = ", ".join(profile.goals) if profile.goals else "none"
                char_lines.append(f"- {name}: {profile.description} (Goals: {goals_str})")
            else:
                char_lines.append(f"- {name}")
        return "\n".join(char_lines)

    async def select_next_speaker(self, story_state: StoryState,
                                   available_characters: List[str]) -> Tuple[str, str]:
        """Decide who speaks next."""
        if story_state.dialogue_history:
            recent_dialogue = "\n".join(
                f"{turn.speaker}: {turn.dialogue}"
                for turn in story_state.dialogue_history[-5:]
            )
        else:
            recent_dialogue = "No dialogue yet. The story is just starting. Select the character most likely to speak first based on the Context."

        character_descriptions = self._build_character_descriptions(
            story_state, available_characters
        )

        prompt = self.prompts["director_select_speaker"].format(
            description=story_state.seed_story.get('description', ''),
            world_state_text=self._format_world_state(story_state),
            recent_dialogue=recent_dialogue,
            character_descriptions=character_descriptions,
            current_turn=story_state.current_turn,
            max_turns=self.config.max_turns,
            action_count=get_action_count(story_state),
            max_consecutive=self.config.max_consecutive_same_character
        )

        response = await self.generate_response(prompt)

        try:
            cleaned_response = self._clean_json_response(response)
            data = json.loads(cleaned_response)
            next_speaker = data.get("next_speaker")
            narration = data.get("narration")
            self.last_selection = {"requested": next_speaker}

            if next_speaker not in available_characters:
                self.last_selection["override"] = f"'{next_speaker}' is not a character"
                next_speaker = available_characters[0]

            # HARD ENFORCEMENT 1: prevent same speaker as last turn
            max_consec = self.config.max_consecutive_same_character
            if len(story_state.dialogue_history) >= max_consec:
                last_speakers = [t.speaker for t in story_state.dialogue_history[-max_consec:]]
                if all(s == next_speaker for s in last_speakers):
                    alternatives = [c for c in available_characters if c != next_speaker]
                    if alternatives:
                        forced = alternatives[0]
                        print(f"  [Anti-Repetition] Blocked {next_speaker} (spoke {max_consec}x in a row), forcing {forced}")
                        self.last_selection["override"] = f"anti-repetition: {next_speaker} just spoke"
                        next_speaker = forced

            # HARD ENFORCEMENT 2: prevent same 2 characters ping-ponging for 4+ turns
            if len(story_state.dialogue_history) >= 4:
                last_4 = [t.speaker for t in story_state.dialogue_history[-4:]]
                unique_in_last_4 = set(last_4)
                if len(unique_in_last_4) == 2 and next_speaker in unique_in_last_4:
                    alternatives = [c for c in available_characters if c not in unique_in_last_4]
                    if alternatives:
                        forced = alternatives[0]
                        print(f"  [Anti-PingPong] Blocked 2-char loop ({unique_in_last_4}), forcing {forced}")
                        self.last_selection["override"] = f"anti-ping-pong: {sorted(unique_in_last_4)} dominated 4 turns"
                        next_speaker = forced

            self.last_selection["chosen"] = next_speaker
            return next_speaker, narration

        except Exception as e:
            salvaged = self._salvage_fields(response, ["next_speaker", "narration"])
            speaker = salvaged.get("next_speaker", "").rstrip("…")
            if speaker in available_characters and salvaged.get("narration"):
                self.last_selection = {"chosen": speaker, "requested": speaker, "parse_error": str(e), "salvaged": True}
                return speaker, salvaged["narration"]
            self.last_selection = {"chosen": available_characters[0], "parse_error": str(e)}
            print(f"Error parsing director selection: {e}")
            print(f"Raw response: {response}")
            return available_characters[0], ""

    async def generate_twist(self, story_state: StoryState) -> Optional[Dict]:
        """Generate a dynamic, context-aware story twist."""
        story_summary = f"Context: {story_state.seed_story.get('description', '')}\n\nDialogue so far:\n" + \
                        "\n".join([f"Turn {t.turn_number} - {t.speaker}: {t.dialogue}"
                                   for t in story_state.dialogue_history[-8:]])

        character_descriptions = self._build_character_descriptions(story_state)

        prompt = self.prompts["director_twist"].format(
            story_summary=story_summary,
            world_state_text=self._format_world_state(story_state),
            character_descriptions=character_descriptions,
            current_turn=story_state.current_turn
        )

        response = await self.generate_response(prompt)

        try:
            cleaned = self._clean_json_response(response)
            data = json.loads(cleaned)
            return data
        except Exception as e:
            print(f"Error parsing director twist: {e}")
            print(f"Raw response: {response}")
            return None

    async def check_conclusion(self, story_state: StoryState) -> Tuple[bool, Optional[str]]:
        """Check if the story should end."""
        action_count = get_action_count(story_state)

        character_descriptions = self._build_character_descriptions(story_state)

        prompt = self.prompts["director_conclusion"].format(
            story_summary=f"Context: {story_state.seed_story.get('description', '')}\nLast Turns:\n" +
                          "\n".join([f"{t.speaker}: {t.dialogue}" for t in story_state.dialogue_history[-10:]]),
            world_state_text=self._format_world_state(story_state),
            character_descriptions=character_descriptions,
            current_turn=story_state.current_turn,
            max_turns=self.config.max_turns,
            action_count=action_count
        )

        response = await self.generate_response(prompt)

        try:
            cleaned_response = self._clean_json_response(response)
            data = json.loads(cleaned_response)
            self.last_conclusion_check = {"should_end": bool(data.get("should_end", False)),
                                          "reason": data.get("reason")}
            return data.get("should_end", False), data.get("conclusion_narration")
        except Exception as e:
            self.last_conclusion_check = {"should_end": False, "parse_error": str(e)}
            print(f"Error parsing director conclusion: {e}")
            return False, None
