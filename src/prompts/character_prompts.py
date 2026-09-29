from ..schemas import CharacterProfile
from ..scenarios import get_character

DEFAULT_PERSONA = "You are a character in a street scene. Speak naturally in Roman Urdu."


def get_character_prompt(character_name: str, character_profile: CharacterProfile,
                         context: str, config, world_state_text: str = "",
                         available_actions: str = "") -> str:
    """Build a character's prompt from the scenario's templates (editable in the admin panel)."""
    scenario = config.scenario
    prompts = scenario["prompts"]
    char = get_character(scenario, character_name)
    persona = char.get("persona") or DEFAULT_PERSONA

    is_english = getattr(config, 'language', 'urdu') == 'english'

    if is_english:
        language_rule = ""
        english_final = prompts["character_language_english"].format(
            character_name=character_name,
            english_style=char.get("english_style") or "English appropriate to your character personality.",
        )
    else:
        language_rule = prompts["character_language_urdu"].format(character_name=character_name)
        english_final = ""

    return prompts["character"].format(
        persona=persona,
        context=context,
        world_state_text=world_state_text if world_state_text else "Nothing notable yet.",
        language_rule=language_rule,
        english_final=english_final,
        character_name=character_name,
        max_dialogue_length=config.max_dialogue_length,
    )
