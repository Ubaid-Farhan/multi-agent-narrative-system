import asyncio
import json
import os
import re
import time
from datetime import datetime
from abc import ABC
from typing import Dict, List, Tuple
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from ..config import StoryConfig

# Gemini 2.5 counts its hidden "thinking" against the output limit, so a low limit cuts answers mid-JSON.
GEMINI_MIN_OUTPUT_TOKENS = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "8192"))

# Models that failed recently are skipped until this time (shared by all agents and runs in the process).
_cooldown_until: Dict[str, float] = {}


class LLMUnavailableError(RuntimeError):
    """Every model in the chain failed (quota used up, overloaded, bad key…). The story cannot continue."""


def _classify(error: str) -> Tuple[str, float]:
    """(kind, seconds to skip this model) for an LLM error."""
    text = error.lower()
    if "perday" in text or "per day" in text or ("free_tier" in text and "429" in text and "quota" in text):
        return "daily quota used up", 3600
    if "429" in error or "resource_exhausted" in text or "rate limit" in text:
        match = re.search(r"retry in ([\d.]+)s", text)
        return "rate limited", min(float(match.group(1)) + 1, 120) if match else 30
    if any(t in text for t in ("503", "unavailable", "overloaded", "high demand")):
        return "overloaded", 20
    if any(t in text for t in ("name resolution", "cannot connect", "timed out", "timeout", "connection")):
        return "network error", 10
    if "empty response" in text:
        return "empty response", 5
    if any(t in text for t in ("401", "403", "api key", "api_key", "permission", "unauthorized", "billing",
                               "insufficient_quota")):
        return "key rejected", 3600
    return "error", 300  # e.g. 400 bad request: don't hammer a model that rejects our request


def _openai_kwargs(model: str, config: StoryConfig) -> Dict:
    kwargs = {"model": model, "max_tokens": config.max_tokens_per_prompt, "max_retries": 0, "timeout": 120}
    if not re.match(r"^(o\d|gpt-5)", model):  # reasoning models only accept the default temperature
        kwargs["temperature"] = config.temperature
    return kwargs


class BaseAgent(ABC):
    def __init__(self, name: str, config: StoryConfig):
        self.name = name
        self.config = config
        self.logs = []
        self.models: List[Tuple[str, object]] = self._build_models(config)
        self.max_wait = 60  # seconds to wait for a model to come back when all are cooling down

    @staticmethod
    def _build_models(config: StoryConfig) -> List[Tuple[str, object]]:
        """Gemini primary, then backup Gemini models, then OpenAI (if OPENAI_API_KEY is set), in order."""
        models = []
        names = [config.model_name] + [m for m in config.gemini_fallback_models if m != config.model_name]
        for name in dict.fromkeys(names):
            models.append((name, ChatGoogleGenerativeAI(
                model=name,
                temperature=config.temperature,
                max_output_tokens=max(config.max_tokens_per_prompt, GEMINI_MIN_OUTPUT_TOKENS),
                max_retries=0,
            )))
        if os.getenv("OPENAI_API_KEY"):
            models.append((config.fallback_model_name, ChatOpenAI(**_openai_kwargs(config.fallback_model_name, config))))
        return models

    @staticmethod
    def _build_llm(config: StoryConfig):
        """The whole chain as one runnable (used for the quick 'is the AI up?' check)."""
        models = [m for _, m in BaseAgent._build_models(config)]
        return models[0].with_fallbacks(models[1:]) if len(models) > 1 else models[0]

    async def generate_response(self, prompt: str) -> str:
        """
        Try each model in order, skipping ones that failed recently. Every attempt is logged to the run
        recorder with the model that answered (or why it failed). Raises LLMUnavailableError when no model
        can answer, so a story stops cleanly instead of continuing with empty turns.
        """
        recorder = getattr(self.config, "recorder", None)
        messages = [("human", prompt)]
        failures: List[str] = []
        for round_no in range(3):
            tried = False
            for model_name, llm in self.models:
                if _cooldown_until.get(model_name, 0) > time.monotonic():
                    continue
                tried = True
                started = time.monotonic()
                try:
                    response = await llm.ainvoke(messages)
                    content = response.text if isinstance(response.content, list) else response.content
                    if not (content or "").strip():
                        raise ValueError("Empty response from LLM")
                    self._log_interaction(prompt, content)
                    if recorder:
                        meta = getattr(response, "response_metadata", None) or {}
                        recorder.llm_call(self.name, meta.get("model_name") or meta.get("model") or model_name,
                                          prompt, content, True, latency_ms=int((time.monotonic() - started) * 1000))
                    return content
                except Exception as e:
                    err = str(e)
                    kind, skip_seconds = _classify(err)
                    _cooldown_until[model_name] = time.monotonic() + skip_seconds
                    failures.append(f"{model_name}: {kind}")
                    print(f"LLM {model_name} failed for {self.name} ({kind}); trying the next model.")
                    if recorder:
                        recorder.llm_call(self.name, model_name, prompt, "", False, error=f"{kind}: {err[:1800]}",
                                          latency_ms=int((time.monotonic() - started) * 1000))
            # Every model is cooling down. Wait for the soonest one, unless all are out for a long time.
            soonest = min((_cooldown_until.get(n, 0) for n, _ in self.models), default=0) - time.monotonic()
            if round_no == 2 or soonest > 120 or soonest > self.max_wait or (not tried and soonest <= 0):
                break
            if soonest > 0:
                wait = min(soonest, self.max_wait)
                print(f"All models busy for {self.name}; waiting {wait:.0f}s…")
                await asyncio.sleep(wait)

        summary = "; ".join(dict.fromkeys(failures)) or "all models are cooling down after earlier failures"
        print(f"Error generating response for {self.name}: no model available ({summary})")
        if recorder:
            recorder.event("error", content=f"{self.name}: no AI model could answer", agent=self.name, error=summary)
        raise LLMUnavailableError(summary)

    def _log_interaction(self, prompt: str, response: str):
        """Log interaction to memory."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "agent": self.name,
            "prompt": prompt,
            "response": response
        }
        self.logs.append(entry)

    def _clean_json_response(self, response: str) -> str:
        """Clean markdown formatting from JSON response."""
        cleaned = response.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0]
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0]
        return cleaned.strip()

    @staticmethod
    def _salvage_fields(response: str, keys: List[str]) -> Dict:
        """Pull string fields out of a cut-off / broken JSON answer (e.g. the model hit its token limit)."""
        found = {}
        for key in keys:
            match = re.search(r'"%s"\s*:\s*"((?:[^"\\]|\\.)*)("?)' % re.escape(key), response, flags=re.S)
            if not match:
                continue
            raw, closed = match.group(1), match.group(2)
            try:
                value = json.loads(f'"{raw}"')
            except json.JSONDecodeError:
                value = raw.replace('\\"', '"').replace("\\n", "\n")
            value = value.strip()
            if value:
                found[key] = value if closed else value.rstrip(" ,.;") + "…"
        return found
