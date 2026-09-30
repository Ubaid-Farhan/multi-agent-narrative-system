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
from src.scenarios import DEFAULT_SCENARIO_ID
from src import db
from src import scenario_store as store
from src.run_recorder import RunRecorder

async def main():
    # Load scenario (story, characters, prompts) — pass an id as argv[1] to pick another one
    scenario_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SCENARIO_ID
    await db.init_db()
    scenario = await store.load_scenario(scenario_id)
    seed_story = {k: scenario.get(k) for k in ("title", "description", "setting")}
    char_configs = {"characters": scenario["characters"]}

    # Initialize config
    config = StoryConfig.from_scenario(scenario)

    # Record the run in the database (no-op without DATABASE_URL)
    recorder = RunRecorder(scenario, config.language, source="cli")
    await recorder.start()
    config.recorder = recorder

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
    try:
        final_state = await story_graph.run(
            seed_story=seed_story,
            character_profiles=story_manager.state.character_profiles,
            character_memories=story_manager.state.character_memories
        )
    except BaseException as e:
        await recorder.finish("aborted" if isinstance(e, KeyboardInterrupt) else "failed", error=str(e))
        await db.close_db()
        raise

    from src.api import events_to_frontend_turns
    speaker_keys = {c["name"]: c["key"] for c in scenario["characters"]}
    turns = events_to_frontend_turns(final_state.get("events", []), seed_story, None, speaker_keys)["turns"]
    conclusion = final_state.get("conclusion_reason") or ""
    await recorder.finish("completed" if db.is_complete(turns, conclusion) else "incomplete", turns=turns,
                          conclusion=conclusion, turn_count=len(turns),
                          action_count=sum(1 for t in turns if t.get("actionText")))
    if recorder.run_id:
        print(f"Run #{recorder.run_id} saved to the database.")
    
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
    
    output_path.write_text(json.dumps(output_data, indent=2, default=str), encoding="utf-8")
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
    prompts_path.write_text(json.dumps(all_logs, indent=2, default=str), encoding="utf-8")
    print(f"Prompts saved to {prompts_path}")
    await db.close_db()

if __name__ == "__main__":
    asyncio.run(main())
