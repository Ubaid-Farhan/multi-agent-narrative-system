"""
Action System for AI Narrative Engine.

Open-ended action system — characters can perform ANY physical action
that makes sense in context. The system categorizes and tracks them
for world_state updates and memory propagation.
"""

from typing import Dict, List, Optional, Tuple
from .schemas import StoryState


_NO_TARGET = {"", "null", "none", "nil", "n/a", "na", "nobody", "no one", "self"}


def normalize_target(target) -> Optional[str]:
    """Models sometimes write the string "null" / "none" for no target — treat those as no target."""
    if target is None:
        return None
    text = str(target).strip()
    return None if text.lower() in _NO_TARGET else text


def validate_action(action_type: str, actor: str, target: Optional[str],
                    state: StoryState) -> Tuple[bool, str]:
    """
    Validate whether an action is allowed. Open-ended — any action type is valid, and the target may be a
    character or anything in the scene ("crowd", "counter", "rickshaw"…).
    """
    if not action_type or not action_type.strip():
        return False, "Empty action type"

    if target and actor == target:
        return False, "Cannot target yourself"

    return True, "Valid"


def execute_action(action_type: str, actor: str, target: Optional[str],
                   description: str, state: StoryState) -> Dict:
    """
    Execute an action and return state updates.
    Handles both known action patterns and free-form actions.

    Returns a dict with keys: world_state, character_memories, narration
    """
    updated_world = dict(state.world_state)
    updated_memories = dict(state.character_memories)

    # Normalize action type for matching
    action_lower = action_type.lower().replace(" ", "_").replace("-", "_")

    # Pattern-match common action categories for world_state updates
    if "money" in action_lower or "pay" in action_lower or "give" in action_lower:
        updated_world["money_exchanged"] = True
        updated_world["money_from"] = actor
        updated_world["money_to"] = target
        narration = f"{actor} hands over money to {target}. {description}"

    elif "bribe" in action_lower or "chai_pani" in action_lower:
        updated_world["bribe_offered"] = True
        updated_world["bribe_from"] = actor
        updated_world["bribe_to"] = target
        narration = f"{actor} subtly offers chai-pani to {target}. {description}"

    elif "challan" in action_lower or "ticket" in action_lower or "fine" in action_lower:
        updated_world["challan_written"] = True
        updated_world["challan_target"] = target
        narration = f"{actor} starts writing a challan for {target}. {description}"

    elif "key" in action_lower or "confiscate" in action_lower or "snatch" in action_lower:
        updated_world["keys_confiscated"] = True
        updated_world["keys_taken_from"] = target or actor
        narration = f"{actor} snatches keys. {description}"

    elif "record" in action_lower or "video" in action_lower or "film" in action_lower:
        updated_world["being_recorded"] = True
        updated_world["recorder"] = actor
        narration = f"{actor} starts recording. {description}"

    elif "block" in action_lower or "stand_in_front" in action_lower:
        updated_world["vehicle_blocked"] = True
        updated_world["vehicle_blocked_by"] = actor
        narration = f"{actor} physically blocks the way. {description}"

    elif "show" in action_lower or "display" in action_lower or "hold_up" in action_lower:
        updated_world[f"{actor}_showed_something"] = True
        narration = f"{actor} shows something — {description}"

    elif "call" in action_lower or "phone" in action_lower or "dial" in action_lower:
        updated_world[f"{actor}_made_call"] = True
        narration = f"{actor} makes a call — {description}"

    elif "chai" in action_lower or "tea" in action_lower:
        updated_world["chai_offered"] = True
        narration = f"{actor} arranges chai. {description}"

    elif "sit" in action_lower or "ground" in action_lower or "collapse" in action_lower:
        updated_world[f"{actor}_on_ground"] = True
        narration = f"{actor} sits/collapses on the ground. {description}"

    elif "push" in action_lower or "shove" in action_lower or "grab" in action_lower:
        updated_world[f"physical_confrontation_{actor}"] = True
        narration = f"{actor} gets physical — {description}"

    elif "cry" in action_lower or "wail" in action_lower or "sob" in action_lower:
        updated_world[f"{actor}_crying"] = True
        narration = f"{actor} breaks down emotionally. {description}"

    elif "whistle" in action_lower or "blow" in action_lower:
        updated_world["whistle_blown"] = True
        narration = f"{actor} blows whistle. {description}"

    else:
        # Free-form action — still tracked
        safe_key = action_type.lower().replace(" ", "_")[:30]
        updated_world[f"action_{safe_key}_{actor}"] = True
        narration = f"{actor}: {description}"

    # Update memory for all characters about the action
    action_fact = f"[ACTION] {actor}: {action_type}" + (f" → {target}" if target else "") + f" ({description})"
    for char_name in state.character_profiles:
        char_mem = list(updated_memories.get(char_name, []))
        char_mem.append(action_fact)
        if len(char_mem) > 20:
            char_mem = char_mem[-20:]
        updated_memories[char_name] = char_mem

    return {
        "world_state": updated_world,
        "character_memories": updated_memories,
        "narration": narration
    }


def get_action_count(state: StoryState) -> int:
    """Count how many action events have occurred so far."""
    return sum(1 for e in state.events if e.get("type") == "action")
