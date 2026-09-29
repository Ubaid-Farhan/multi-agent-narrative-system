import asyncio
import json
import os
from datetime import datetime
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from ..config import StoryConfig

class BaseAgent(ABC):
    def __init__(self, name: str, config: StoryConfig):
        self.name = name
        self.config = config
        self.logs = []
        self.llm = self._build_llm(config)

    @staticmethod
    def _build_llm(config: StoryConfig):
        """Gemini primary, then backup Gemini models, then OpenAI (if OPENAI_API_KEY is set)."""
        def gemini(model: str):
            return ChatGoogleGenerativeAI(
                model=model,
                temperature=config.temperature,
                max_output_tokens=config.max_tokens_per_prompt,
                max_retries=1,
            )

        primary = gemini(config.model_name)
        fallbacks = [gemini(m) for m in config.gemini_fallback_models if m != config.model_name]
        if os.getenv("OPENAI_API_KEY"):
            fallbacks.append(ChatOpenAI(
                model=config.fallback_model_name,
                temperature=config.temperature,
                max_tokens=config.max_tokens_per_prompt,
            ))
        return primary.with_fallbacks(fallbacks) if fallbacks else primary

    async def generate_response(self, prompt: str) -> str:
        """Generate a response using the LLM."""
        # Transient failures: rate limit, overloaded model, network/DNS blips.
        transient = ("429", "503", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "name resolution",
                     "Cannot connect", "timed out", "Timeout", "Empty response")
        attempts = 4
        for attempt in range(attempts):
            try:
                messages = [("human", prompt)]
                response = await self.llm.ainvoke(messages)
                content = response.text if isinstance(response.content, list) else response.content
                if not content.strip():
                    raise ValueError("Empty response from LLM")
                self._log_interaction(prompt, content)
                return content
            except Exception as e:
                err = str(e)
                if any(t in err for t in transient) and attempt < attempts - 1:
                    wait = 10 * (attempt + 1)
                    print(f"LLM temporarily unavailable for {self.name} ({err[:80]}), retrying in {wait}s...")
                    await asyncio.sleep(wait)
                    continue
                print(f"Error generating response for {self.name}: {e}")
                return ""

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
