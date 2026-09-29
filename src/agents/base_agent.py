import asyncio
import json
import os
from datetime import datetime
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from langchain_openai import ChatOpenAI
from ..config import StoryConfig

class BaseAgent(ABC):
    def __init__(self, name: str, config: StoryConfig):
        self.name = name
        self.config = config
        self.logs = []
        self.llm = ChatOpenAI(
            model=config.model_name,
            temperature=config.temperature,
            max_tokens=config.max_tokens_per_prompt,
        )
    
    async def generate_response(self, prompt: str) -> str:
        """Generate a response using the LLM."""
        for attempt in range(3):
            try:
                messages = [("human", prompt)]
                response = await self.llm.ainvoke(messages)
                self._log_interaction(prompt, response.content)
                return response.content
            except Exception as e:
                err = str(e)
                if "429" in err and attempt < 2:
                    wait = 15 * (attempt + 1)
                    print(f"Rate limit hit, waiting {wait}s...")
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
