"""
AI images for scenarios: character portraits and scene backgrounds.

Uses Cloudflare Workers AI (default model: FLUX.1 [schnell], open weights, free daily allowance of
10,000 neurons ≈ 170 images). Enabled when CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN are set.
Generated images are stored in the database like uploaded ones (see scenario_store.save_image).
"""
import asyncio
import base64
import os
import re
from typing import Dict, List, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("CF_IMAGE_MODEL", "@cf/black-forest-labs/flux-1-schnell")
STEPS = int(os.getenv("CF_IMAGE_STEPS", "6"))  # 1-8; more steps = better detail, more neurons
TIMEOUT = float(os.getenv("CF_IMAGE_TIMEOUT", "120"))
STYLE = os.getenv(
    "IMAGE_STYLE",
    "semi-realistic digital illustration, cinematic lighting, rich detail, warm colour grading, "
    "consistent graphic-novel art style",
)
MAX_PROMPT = 2000  # the model accepts up to 2048 characters
PARALLEL = 2


class ImageGenerationError(RuntimeError):
    pass


def enabled() -> bool:
    return bool(os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip() and os.getenv("CLOUDFLARE_API_TOKEN", "").strip())


def info() -> Dict:
    return {"enabled": enabled(), "model": MODEL}


# ─────────────────────────────── prompts ───────────────────────────────

def _clean(text, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def _setting_text(setting, limit: int = 500) -> str:
    """Flatten the setting dict (nested values too) into 'key: value' phrases."""
    parts: List[str] = []

    def walk(value, prefix=""):
        if isinstance(value, dict):
            for k, v in value.items():
                walk(v, f"{k.replace('_', ' ')}")
        elif isinstance(value, list):
            for v in value:
                walk(v, prefix)
        elif value not in (None, ""):
            parts.append(f"{prefix}: {value}" if prefix else str(value))

    walk(setting or {})
    return _clean("; ".join(parts), limit)


def _location(scenario: Dict) -> str:
    setting = scenario.get("setting") or {}
    loc = setting.get("location") if isinstance(setting, dict) else None
    return _clean(loc or scenario.get("subtitle") or "", 160)


def character_prompt(scenario: Dict, character: Dict) -> str:
    who = character.get("label") or character.get("name") or "a character"
    place = _location(scenario)
    prompt = (
        f"Character portrait of {_clean(who, 120)}. {_clean(character.get('description'), 700)} "
        f"{'Setting: ' + place + '. ' if place else ''}"
        "Waist-up portrait, facing the viewer, expressive face showing their mood, clothing and props true to "
        "their role and the setting. Single person, centred, plain soft neutral background. "
        f"Style: {STYLE}. No text, no captions, no watermark."
    )
    return prompt[:MAX_PROMPT]


def background_prompt(scenario: Dict) -> str:
    prompt = (
        f"Wide cinematic establishing shot of the scene \"{_clean(scenario.get('title'), 120)}\". "
        f"{_setting_text(scenario.get('setting'))}. {_clean(scenario.get('description'), 700)} "
        "Show the location and atmosphere; people only as a distant background crowd, no close-up faces. "
        f"Style: {STYLE}. No text, no signs with readable words, no watermark."
    )
    return prompt[:MAX_PROMPT]


# ─────────────────────────────── generation ───────────────────────────────

async def generate(prompt: str, seed: Optional[int] = None) -> bytes:
    """Run the text-to-image model and return JPEG bytes."""
    if not enabled():
        raise ImageGenerationError("Image generation is off: set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN in .env "
                                   "and restart the API.")
    prompt = (prompt or "").strip()
    if not prompt:
        raise ImageGenerationError("The image prompt is empty.")
    account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{MODEL}"
    body = {"prompt": prompt[:MAX_PROMPT], "steps": max(1, min(STEPS, 8))}
    if seed is not None:
        body["seed"] = seed
    headers = {"Authorization": f"Bearer {os.getenv('CLOUDFLARE_API_TOKEN', '').strip()}"}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            res = await client.post(url, json=body, headers=headers)
    except httpx.HTTPError as e:
        raise ImageGenerationError(f"Could not reach Cloudflare: {e.__class__.__name__}") from e
    try:
        data = res.json()
    except ValueError:
        data = {}
    if res.status_code != 200 or not data.get("success", True):
        errors = "; ".join(str(e.get("message", e)) for e in data.get("errors", []) if e) or res.text[:300]
        if res.status_code in (401, 403):
            raise ImageGenerationError(f"Cloudflare rejected the API token ({res.status_code}). It needs the "
                                       f"'Workers AI' permission. {errors}")
        if res.status_code == 429 or "neuron" in errors.lower() or "limit" in errors.lower():
            raise ImageGenerationError(f"Cloudflare's daily free image limit is used up. Try again tomorrow. {errors}")
        raise ImageGenerationError(f"Cloudflare image generation failed ({res.status_code}): {errors}")
    image = (data.get("result") or {}).get("image")
    if not image:
        raise ImageGenerationError("Cloudflare returned no image.")
    return base64.b64decode(image)


async def generate_scenario_images(scenario: Dict, save, on_progress=None) -> List[str]:
    """
    Fill in missing background/character images of a (new) scenario in place.
    `save(filename, raw) -> url` stores an image. Returns warnings; never raises for one failed image.
    """
    jobs = []
    if not scenario.get("background_image"):
        jobs.append(("background", "Scene background", background_prompt(scenario), None))
    for char in scenario.get("characters", []):
        if not char.get("image"):
            jobs.append(("character", char.get("name") or "Character", character_prompt(scenario, char), char))

    warnings: List[str] = []
    sem = asyncio.Semaphore(PARALLEL)
    done = 0

    async def run(kind, label, prompt, char):
        nonlocal done
        async with sem:
            try:
                raw = await generate(prompt)
                slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or kind
                url = await save(f"ai-{slug}.jpg", raw)
                if kind == "background":
                    scenario["background_image"] = url
                else:
                    char["image"] = url
            except Exception as e:
                warnings.append(f"Image for {label} failed: {e}")
            finally:
                done += 1
                if on_progress:
                    await on_progress(f"Images: {done}/{len(jobs)} done")

    await asyncio.gather(*(run(*job) for job in jobs))
    return warnings
