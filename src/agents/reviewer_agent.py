import json
from typing import Dict, Optional, Tuple
from .base_agent import BaseAgent
from ..config import StoryConfig
from ..schemas import StoryState


REVIEWER_PROMPT_URDU = """You are a KARACHI STREET SCENE REVIEWER. You are a born-and-raised Karachiite who has lived on Shahrah-e-Faisal for 40 years. You know EXACTLY how people talk, act, and behave in these situations.

Your job: Review this character's dialogue and action for REALISM and QUALITY. You are harsh but fair.

CHARACTER: {character_name}
CHARACTER BACKGROUND: {character_description}

WHAT THEY JUST SAID:
"{dialogue}"

ACTION THEY PERFORMED: {action_text}

THEIR PREVIOUS LINES (for repetition check):
{previous_lines}

CURRENT SITUATION:
{world_state}

=== CHECK THESE THINGS ===

1. **LANGUAGE REALISM**:
   - If this is Saleem (poor rickshaw driver): Is he speaking too much English? A real rickshaw driver in Karachi speaks 95% Urdu. Words like "injustice", "harassing", "obstructing" are TOO educated for him.
   - If this is Ahmed (businessman): Is he code-switching naturally? Elite Karachiites mix English-Urdu mid-sentence.
   - If this is Raza (constable): Is he being too polite? A Karachi traffic cop says "oye sun!" not "excuse me sir."
   - If this is Jameel (uncle): Is he dramatic enough? Is he inserting himself physically?

2. **LOGICAL CONSISTENCY**:
   - Does the dialogue make sense given what JUST happened?
   - If someone offered 20,000 rupees to a man who earns 800/day, would he really refuse? (NO — that's unrealistic)
   - If keys are confiscated, is the character acknowledging they can't leave?
   - Are amounts realistic? (A rickshaw bumper costs 2000-5000, not 50,000)

3. **REPETITION**:
   - Is the character saying the SAME thing they said in previous turns, just rephrased?
   - Are they using the SAME emotional appeal again? (e.g., "my children" for the 4th time)
   - Are they making the same argument with different words?

4. **ACTION LOGIC**:
   - Does the physical action make sense in this moment?
   - Would a real person do this right now, or is it forced/random?
   - If no action: is that appropriate? (Not every turn needs an action)

Respond with JSON ONLY:
{{
    "approved": true/false,
    "issues": ["list of specific problems found"] or [],
    "severity": "minor" or "major" or "none",
    "suggestion": "If rejected, what should the character do/say instead? (1 sentence)" or null
}}

Be STRICT. If the dialogue sounds like a soap opera instead of a real Karachi street, reject it.
If the language is wrong for the character's education level, reject it.
If they are repeating themselves, reject it.
Minor issues (small phrasing problems) can be approved with notes.
Major issues (wrong language, unrealistic behavior, blatant repetition) must be rejected.
"""

REVIEWER_PROMPT_ENGLISH = """You are a KARACHI STREET SCENE REVIEWER reviewing an ENGLISH-MODE story. All characters speak English — this is intentional and correct. DO NOT flag or reject anyone for speaking English.

Your job: Review this character's dialogue and action for QUALITY. Be harsh but fair.

CHARACTER: {character_name}
CHARACTER BACKGROUND: {character_description}

WHAT THEY JUST SAID:
"{dialogue}"

ACTION THEY PERFORMED: {action_text}

THEIR PREVIOUS LINES (for repetition check):
{previous_lines}

CURRENT SITUATION:
{world_state}

=== CHECK THESE THREE THINGS ONLY ===

1. **REPETITION** (most important check):
   - Is the character saying the SAME thing as a previous turn, just rephrased?
   - Same emotional appeal again? (e.g., "my children" for the 4th time, or offering money for the 3rd time)
   - Same argument recycled with different words?

2. **LOGICAL CONSISTENCY**:
   - Does the dialogue make sense given what JUST happened?
   - If 20,000 rupees was offered to someone earning 800/day, would they really refuse?
   - Are amounts realistic? (Rickshaw bumper = 2000-5000 rupees)

3. **CHARACTER PERSONALITY** (tone/attitude — NOT language):
   - Saleem: Is he desperate and street-smart? Does he switch tactics?
   - Ahmed: Is he arrogant and impatient? Does his composure crack as time passes?
   - Raza: Is he gruff, commanding, transparently corrupt? Short sentences?
   - Jameel: Is he theatrical, self-important, chaotic? Does he make things worse?

DO NOT check or flag:
- Language (English is correct for all characters in this mode)
- Grammar (broken English for working class is intentional)
- "Too formal" or "too educated" — irrelevant in English mode

Respond with JSON ONLY:
{{
    "approved": true/false,
    "issues": ["list of specific problems found"] or [],
    "severity": "minor" or "major" or "none",
    "suggestion": "If rejected, what should the character do/say instead? (1 sentence)" or null
}}

Only reject for MAJOR repetition or severe logic breaks.
Minor phrasing issues: approve with notes, do not reject.
"""


class ReviewerAgent(BaseAgent):
    """Reviews character outputs for Karachi realism, logical consistency, and repetition."""

    def __init__(self, config: StoryConfig):
        super().__init__("Reviewer", config)

    async def review_turn(self, character_name: str, dialogue: str,
                          action: Optional[Dict], state: StoryState) -> Tuple[bool, str]:
        """
        Review a character's dialogue and action.

        Returns:
            (approved: bool, feedback: str)
            If not approved, feedback contains the suggestion for regeneration.
        """
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
        prompt_template = REVIEWER_PROMPT_ENGLISH if is_english else REVIEWER_PROMPT_URDU

        prompt = prompt_template.format(
            character_name=character_name,
            character_description=character_description,
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
            return True, ""
