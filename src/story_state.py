from typing import List, Dict, Tuple, Optional
from datetime import datetime
from .schemas import StoryState, CharacterProfile, DialogueTurn
from .config import StoryConfig

MAX_MEMORY_FACTS = 20

class StoryStateManager:
    def __init__(self, seed_story: Dict, characters: List[Dict], config: StoryConfig):
        self.config = config
        self.state = StoryState(
            seed_story=seed_story,
            character_profiles={
                char["name"]: CharacterProfile(
                    name=char["name"],
                    description=char["description"],
                    goals=char.get("goals", []),
                    inventory=char.get("inventory", []),
                ) for char in characters
            },
            character_memories={char["name"]: [] for char in characters},
            world_state={}
        )

    def add_turn(self, speaker: str, dialogue: str, metadata: Dict = None) -> None:
        """Add a dialogue turn and increment turn count."""
        turn = DialogueTurn(
            turn_number=self.state.current_turn + 1,
            speaker=speaker,
            dialogue=dialogue,
            metadata=metadata or {}
        )
        self.state.dialogue_history.append(turn)
        self.state.current_turn += 1

    @staticmethod
    def update_memory(state: StoryState, character_name: str, fact: str) -> None:
        """Append a fact to a character's memory, capping at MAX_MEMORY_FACTS."""
        if character_name not in state.character_memories:
            state.character_memories[character_name] = []
        state.character_memories[character_name].append(fact)
        # Cap memory size
        if len(state.character_memories[character_name]) > MAX_MEMORY_FACTS:
            state.character_memories[character_name] = state.character_memories[character_name][-MAX_MEMORY_FACTS:]

    def get_context_for_character(self, character_name: str) -> str:
        """Return relevant context for a character including memory, goals, inventory, and dialogue."""
        profile = self.state.character_profiles.get(character_name)

        # Goals
        goals_text = "\n".join(f"- {g}" for g in profile.goals) if profile and profile.goals else "None"

        # Inventory
        inventory_text = ", ".join(profile.inventory) if profile and profile.inventory else "Nothing"

        # Memory facts
        memories = self.state.character_memories.get(character_name, [])
        memory_text = "\n".join(f"- {m}" for m in memories[-10:]) if memories else "No memories yet."

        # Dialogue context: own lines + others' lines (last 15 turns)
        recent_turns = self.state.dialogue_history[-15:]
        history_text = "\n".join([
            f"{turn.speaker}: {turn.dialogue}"
            for turn in recent_turns
        ])

        return f"""Initial Event: {self.state.seed_story.get('description', 'Unknown event')}

Your Goals:
{goals_text}

Your Inventory: {inventory_text}

Your Memory (things you remember):
{memory_text}

Recent Dialogue:
{history_text}
"""

    def get_context_for_director(self) -> str:
        """Return full story context for director decisions."""
        history_text = "\n".join([
            f"[{turn.turn_number}] {turn.speaker}: {turn.dialogue}"
            for turn in self.state.dialogue_history
        ])

        return f"""
    Story Title: {self.state.seed_story.get('title', 'Untitled')}
    Description: {self.state.seed_story.get('description', '')}

    Dialogue History:
    {history_text}

    Director Notes:
    {chr(10).join(self.state.director_notes)}
"""

    def should_end_story(self) -> Tuple[bool, str]:
        """Check if story should conclude based on turn limits."""
        if self.state.current_turn >= self.config.max_turns:
            return True, "Max turns reached"
        if self.state.is_concluded:
            return True, self.state.conclusion_reason or "Director concluded story"
        return False, ""
