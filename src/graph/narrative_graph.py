import json
from typing import Dict, List, Any, Optional
from langgraph.graph import StateGraph, END
from ..config import StoryConfig
from ..schemas import StoryState, DialogueTurn
from ..agents.character_agent import CharacterAgent
from ..agents.director_agent import DirectorAgent
from ..agents.reviewer_agent import ReviewerAgent
from ..story_state import StoryStateManager
from ..actions import validate_action, execute_action, get_action_count
from ..prompts.character_prompts import CHARACTER_APPEALS


def _build_appeal_decay_text(character_name: str, dialogue_history) -> str:
    """Scan dialogue history and return appeal impact status for this character."""
    appeals = CHARACTER_APPEALS.get(character_name)
    if not appeals:
        return ""

    my_lines = [t.dialogue.lower() for t in dialogue_history if t.speaker == character_name]
    if not my_lines:
        return ""

    decay_labels = {0: "Fresh — high impact", 1: "Used once — still resonates",
                    2: "Crowd tiring — use only if truly necessary", 3: "WORN OUT — crowd numb, hurts you now"}

    lines = []
    for appeal_name, keywords in appeals.items():
        count = sum(1 for line in my_lines if any(kw.lower() in line for kw in keywords))
        label = decay_labels.get(min(count, 3))
        lines.append(f"  - {appeal_name}: used {count}x → {label}")

    return "APPEAL IMPACT STATUS (crowd's reaction to each tactic):\n" + "\n".join(lines)


class NarrativeGraph:
    def __init__(self, config: StoryConfig, characters: List[CharacterAgent],
                 director: DirectorAgent, reviewer: Optional[ReviewerAgent] = None):
        self.config = config
        self.characters = {c.name: c for c in characters}
        self.director = director
        self.reviewer = reviewer
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(StoryState)

        workflow.add_node("director_select", self._director_select_node)
        workflow.add_node("character_respond", self._character_respond_node)
        workflow.add_node("check_conclusion", self._check_conclusion_node)
        workflow.add_node("conclude", self._conclude_node)

        workflow.set_entry_point("director_select")
        workflow.add_edge("director_select", "character_respond")
        workflow.add_edge("character_respond", "check_conclusion")

        workflow.add_conditional_edges(
            "check_conclusion",
            self._route_conclusion,
            {
                "conclude": "conclude",
                "continue": "director_select"
            }
        )
        workflow.add_edge("conclude", END)

        return workflow.compile()

    def _format_world_state(self, state: StoryState) -> str:
        """Format world_state dict into readable text for prompts."""
        if not state.world_state:
            return "Nothing notable yet."
        lines = []
        for key, value in state.world_state.items():
            if key.startswith("_"):
                continue  # Skip internal flags
            readable_key = key.replace("_", " ").title()
            lines.append(f"- {readable_key}: {value}")
        return "\n".join(lines) if lines else "Nothing notable yet."

    async def _director_select_node(self, state: StoryState) -> Dict:
        """Director selects the next speaker. Generates twist at turn 9 via LLM."""
        available = list(self.characters.keys())

        twist_narration = ""
        updated_world = dict(state.world_state)
        updated_memories = dict(state.character_memories)

        # === DYNAMIC TWIST GENERATION ===
        # At turn 9, ask the Director to generate a contextual twist
        if state.current_turn == 9 and not state.world_state.get("_twist_injected"):
            twist_data = await self.director.generate_twist(state)

            if twist_data:
                twist_narration = f"\n\n*** DRAMATIC TWIST ***\n{twist_data.get('twist_narration', '')}\n***\n"
                updated_world["_twist_injected"] = True

                # Apply world state updates from the twist
                ws_updates = twist_data.get("world_state_updates", {})
                if isinstance(ws_updates, dict):
                    updated_world.update(ws_updates)

                # Add twist to ALL characters' memories
                memory_update = twist_data.get("memory_update", "A dramatic twist has occurred.")
                for char_name in state.character_profiles:
                    char_mem = list(updated_memories.get(char_name, []))
                    char_mem.append(f"TWIST: {memory_update}")
                    if len(char_mem) > 20:
                        char_mem = char_mem[-20:]
                    updated_memories[char_name] = char_mem

                print(f"\n{'='*60}")
                print(f"STORY TWIST (Director-generated)")
                print(f"{'='*60}\n")

        next_speaker, narration = await self.director.select_next_speaker(state, available)

        # Combine twist narration with director narration
        full_narration = twist_narration + narration if twist_narration else narration

        print("********************************")
        print(f"Director Narration: {full_narration}")
        print(f"Next Speaker: {next_speaker}")
        print("********************************\n")

        events_update = []
        if twist_narration:
            events_update.append({
                "type": "narration",
                "content": twist_narration,
                "turn": state.current_turn,
                "metadata": {"twist": True}
            })
        if narration:
            events_update.append({
                "type": "narration",
                "content": narration,
                "turn": state.current_turn
            })

        return {
            "next_speaker": next_speaker,
            "director_notes": state.director_notes + [f"Selected: {next_speaker}"],
            "story_narration": state.story_narration + [full_narration] if full_narration else state.story_narration,
            "events": state.events + events_update,
            "world_state": updated_world,
            "character_memories": updated_memories
        }

    def _build_character_context(self, state: StoryState, character_name: str) -> str:
        """Build context for a character including goals, inventory, memory, dialogue, and anti-repetition."""
        profile = state.character_profiles.get(character_name)

        goals_text = "\n".join(f"- {g}" for g in profile.goals) if profile and profile.goals else "None"
        inventory_text = ", ".join(profile.inventory) if profile and profile.inventory else "Nothing"

        memories = state.character_memories.get(character_name, [])
        memory_text = "\n".join(f"- {m}" for m in memories[-10:]) if memories else "No memories yet."

        recent_turns = state.dialogue_history[-15:]
        history_text = "\n".join([
            f"{turn.speaker}: {turn.dialogue}"
            for turn in recent_turns
        ])

        narration = state.story_narration[-1] if state.story_narration else ""

        # Build "YOUR previous lines" — so character sees what they already said
        my_previous_lines = [
            f"Turn {t.turn_number}: {t.dialogue[:150]}"
            for t in state.dialogue_history if t.speaker == character_name
        ]
        if my_previous_lines:
            my_lines_text = "\n".join(f"- {l}" for l in my_previous_lines[-5:])
        else:
            my_lines_text = "You haven't spoken yet."

        # Build "actions YOU already performed"
        my_previous_actions = [
            f"{e.get('action_type', '?')}: {e.get('description', '')[:80]}"
            for e in state.events
            if e.get("type") == "action" and e.get("speaker") == character_name
        ]
        if my_previous_actions:
            used_actions_text = "\n".join(f"- {a}" for a in my_previous_actions)
        else:
            used_actions_text = "None yet"

        appeal_decay = _build_appeal_decay_text(character_name, state.dialogue_history)

        return f"""Initial Event: {state.seed_story.get('description', 'Unknown event')}

Director Narration: {narration}

Your Goals:
{goals_text}

Your Inventory: {inventory_text}

Your Memory (things you remember):
{memory_text}

=== YOUR PREVIOUS DIALOGUE (you said these — DO NOT repeat the same points) ===
{my_lines_text}

You MUST say something COMPLETELY DIFFERENT from your previous lines above. Change your tactic, react to what JUST happened, bring up something NEW.

{appeal_decay}

=== YOUR PREVIOUS ACTIONS (you already did these — do something DIFFERENT if you act) ===
{used_actions_text}

If you act physically this turn, do something you haven't done before. But only act if the moment truly calls for it.

Recent Dialogue:
{history_text}
"""

    async def _character_respond_node(self, state: StoryState) -> Dict:
        """Selected character generates dialogue and/or action."""
        next_speaker = state.next_speaker

        if not next_speaker or next_speaker not in self.characters:
            next_speaker = list(self.characters.keys())[0]

        character = self.characters[next_speaker]

        # Build context and world state text
        context = self._build_character_context(state, next_speaker)
        world_state_text = self._format_world_state(state)

        # Get structured response (dialogue + optional action)
        dialogue, action = await character.respond(state, context, world_state_text)

        # ReviewerAgent: check for Karachi realism, logical consistency, repetition
        if self.reviewer:
            approved, feedback = await self.reviewer.review_turn(
                next_speaker, dialogue, action, state
            )
            if not approved and feedback:
                # Retry once with reviewer suggestion in context
                context_retry = context + "\n\n=== REVIEWER FEEDBACK (you must address this) ===\n" + feedback
                dialogue, action = await character.respond(state, context_retry, world_state_text)
                print(f"  [Reviewer] Retry used for {next_speaker}.")

        print("********************************")
        print(f"{next_speaker}: {dialogue}")
        if action:
            print(f"  [ACTION] {action.get('type')}" +
                  (f" → {action.get('target')}" if action.get('target') else "") +
                  f" ({action.get('description', '')})")
        print("********************************\n")

        # Build state updates
        new_turn = DialogueTurn(
            turn_number=state.current_turn + 1,
            speaker=next_speaker,
            dialogue=dialogue
        )

        new_events = []
        updated_world = dict(state.world_state)
        updated_memories = dict(state.character_memories)

        # Add dialogue event
        new_events.append({
            "type": "dialogue",
            "speaker": next_speaker,
            "content": dialogue,
            "turn": state.current_turn + 1
        })

        # Process action if present
        if action and isinstance(action, dict) and action.get("type"):
            action_type = action["type"]
            target = action.get("target")
            description = action.get("description", "")

            is_valid, reason = validate_action(action_type, next_speaker, target, state)

            if is_valid:
                # Execute the action
                result = execute_action(action_type, next_speaker, target, description, state)

                updated_world = result["world_state"]
                updated_memories = result["character_memories"]
                action_narration = result["narration"]

                # Add action event
                new_events.append({
                    "type": "action",
                    "speaker": next_speaker,
                    "action_type": action_type,
                    "target": target,
                    "content": action_narration,
                    "description": description,
                    "turn": state.current_turn + 1
                })

                print(f"  >> Action executed: {action_narration}")
            else:
                print(f"  >> Action rejected: {reason}")

        # Update dialogue memory for all characters
        speaker_mem = list(updated_memories.get(next_speaker, []))
        speaker_mem.append(f"Turn {state.current_turn + 1}: I said: {dialogue[:150]}")
        if len(speaker_mem) > 20:
            speaker_mem = speaker_mem[-20:]
        updated_memories[next_speaker] = speaker_mem

        for char_name in state.character_profiles:
            if char_name != next_speaker:
                other_mem = list(updated_memories.get(char_name, []))
                other_mem.append(f"Turn {state.current_turn + 1}: {next_speaker} said: {dialogue[:150]}")
                if len(other_mem) > 20:
                    other_mem = other_mem[-20:]
                updated_memories[char_name] = other_mem

        return {
            "dialogue_history": state.dialogue_history + [new_turn],
            "current_turn": state.current_turn + 1,
            "events": state.events + new_events,
            "character_memories": updated_memories,
            "world_state": updated_world
        }

    async def _check_conclusion_node(self, state: StoryState) -> Dict:
        """Check if story should end. Enforce min_turns and post-twist breathing room."""
        action_count = get_action_count(state)

        # HARD BLOCK: Do not allow conclusion before min_turns
        if state.current_turn < self.config.min_turns:
            return {"is_concluded": False}

        # HARD BLOCK: Do not allow conclusion before 5 actions
        if action_count < 5:
            return {"is_concluded": False}

        # HARD BLOCK: After a twist is injected (turn 9), give at least 5 more turns
        twist_injected = state.world_state.get("_twist_injected")
        if twist_injected and state.current_turn < 14:
            return {"is_concluded": False}

        # Only check conclusion every OTHER turn after min_turns (prevents immediate ending)
        if state.current_turn < 18 and state.current_turn % 2 != 0:
            return {"is_concluded": False}

        # Force conclusion at max_turns — generate proper narrative
        if state.current_turn >= self.config.max_turns:
            _, narration = await self.director.check_conclusion(state)
            return {
                "is_concluded": True,
                "conclusion_reason": narration or "Shahrah-e-Faisal dheere dheere apni aam zindagi mein wapis aa gaya. Bheed chhant gayi, aur rickshaw aur BMW dono apni raahon pe nikal gaye — jaise yeh sab hua hi nahi tha.",
                "events": state.events + ([{
                    "type": "narration",
                    "content": narration,
                    "turn": state.current_turn,
                    "metadata": {"conclusion": True}
                }] if narration else [])
            }

        should_end, reason = await self.director.check_conclusion(state)

        if should_end:
            events_update = []
            if reason:
                events_update.append({
                    "type": "narration",
                    "content": reason,
                    "turn": state.current_turn,
                    "metadata": {"conclusion": True}
                })

            return {
                "is_concluded": True,
                "conclusion_reason": str(reason),
                "events": state.events + events_update
            }
        return {"is_concluded": False}

    async def _conclude_node(self, state: StoryState) -> Dict:
        """Finalize story with proper ending narration."""
        conclusion = state.conclusion_reason or "The story has concluded."

        print("\n" + "=" * 60)
        print("STORY CONCLUSION")
        print("=" * 60)
        print(conclusion)
        print("=" * 60 + "\n")

        return {"is_concluded": True}

    def _route_conclusion(self, state: StoryState) -> str:
        if state.is_concluded:
            return "conclude"
        return "continue"

    async def run(self, seed_story: Dict, character_profiles: Dict[str, Any] = None,
                  character_memories: Dict[str, list] = None) -> StoryState:
        """Execute the narrative game loop."""
        initial_state = StoryState(
            seed_story=seed_story,
            character_profiles=character_profiles or {},
            dialogue_history=[],
            director_notes=[],
            character_memories=character_memories or {},
            world_state={}
        )

        final_state = await self.graph.ainvoke(initial_state)
        return final_state
