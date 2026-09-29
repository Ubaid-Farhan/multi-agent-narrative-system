import asyncio
import json
import sys
import os
from pathlib import Path

current_dir = Path(__file__).parent
project_root = current_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.config import StoryConfig
from src.agents.character_agent import CharacterAgent
from src.agents.director_agent import DirectorAgent
from src.agents.reviewer_agent import ReviewerAgent
from src.graph.narrative_graph import NarrativeGraph
from src.story_state import StoryStateManager
from src.scenarios import load_scenario, DEFAULT_SCENARIO_ID

async def main():
    # Load scenario (story, characters, prompts) — pass an id as argv[1] to pick another one
    scenario_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SCENARIO_ID
    scenario = load_scenario(scenario_id)
    seed_story = {k: scenario.get(k) for k in ("title", "description", "setting")}
    char_configs = {"characters": scenario["characters"]}

    # Initialize config
    config = StoryConfig.from_scenario(scenario)

    # Create character agents
    characters = [
        CharacterAgent(
            name=char["name"],
            config=config
        )
        for char in char_configs["characters"]
    ]
    
    # Create director and reviewer
    director = DirectorAgent(config)
    reviewer = ReviewerAgent(config)
    
    # Initialize StoryStateManager to prepare initial state properly
    story_manager = StoryStateManager(seed_story, char_configs["characters"], config)
    
    # Build and run narrative graph (reviewer checks each turn for Karachi realism)
    story_graph = NarrativeGraph(config, characters, director, reviewer)
    
    print("Starting Narrative Game...")
    print(f"Title: {seed_story['title']}")
    print(f"Scenario: {seed_story['description']}\n")
    
    # Run the game with the prepared character states (including memory)
    final_state = await story_graph.run(
        seed_story=seed_story,
        character_profiles=story_manager.state.character_profiles,
        character_memories=story_manager.state.character_memories
    )
    
    # Print results
    print("\n=== STORY TRANSCRIPT ===\n")
    for turn in final_state["dialogue_history"]:
        if isinstance(turn, dict):
             print(f"[Turn {turn.get('turn_number')}] {turn.get('speaker')}:")
             print(f"  {turn.get('dialogue')}\n")
        else:
             print(f"[Turn {turn.turn_number}] {turn.speaker}:")
             print(f"  {turn.dialogue}\n")
    
    print(f"\n=== CONCLUSION ===")
    print(f"Ended after {final_state['current_turn']} turns")
    print(f"\n--- Story Ending ---")
    print(f"{final_state.get('conclusion_reason', 'No conclusion narration.')}")
    print(f"--- End ---")

    # Count actions in events
    action_count = sum(1 for e in final_state.get("events", []) if e.get("type") == "action")
    print(f"Total actions performed: {action_count}")

    # Save to JSON
    output_path = project_root / "story_output.json"
    output_data = {
        "title": seed_story.get("title"),
        "seed_story": seed_story,
        "events": final_state.get("events", []),
        "conclusion": final_state.get("conclusion_reason"),
        "metadata": {
            "total_turns": final_state["current_turn"],
            "total_actions": action_count,
            "conclusion_reason": final_state.get("conclusion_reason")
        }
    }
    
    output_path.write_text(json.dumps(output_data, indent=2, default=str))
    print(f"\nStory saved to {output_path}")

    # Save prompts
    all_logs = []
    
    # Director logs
    for log in director.logs:
        log["role"] = "Director"
        all_logs.append(log)
    
    # Reviewer logs
    for log in reviewer.logs:
        log["role"] = "Reviewer"
        all_logs.append(log)
        
    # Character logs
    for char in characters:
        for log in char.logs:
            log["role"] = f"Character ({char.name})"
            all_logs.append(log)
            
    # Sort by timestamp
    all_logs.sort(key=lambda x: x["timestamp"])
    
    prompts_path = project_root / "prompts_log.json"
    prompts_path.write_text(json.dumps(all_logs, indent=2, default=str))
    print(f"Prompts saved to {prompts_path}")

if __name__ == "__main__":
    asyncio.run(main())
