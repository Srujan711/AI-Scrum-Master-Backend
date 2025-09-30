"""
LLM Provider - Supports OpenAI, Ollama, Groq, and other providers
"""
from typing import Dict, Any, Optional
import os
import httpx
from dotenv import load_dotenv
from ..config import settings
from ..utils.logging import get_logger

# Load environment variables
load_dotenv()

logger = get_logger(__name__)


class LLMProvider:
    """Unified interface for different LLM providers"""

    def __init__(self):
        self.provider = self._detect_provider()
        logger.info(f"Initialized LLM provider: {self.provider}")

    def _detect_provider(self) -> str:
        """Detect which LLM provider to use based on configuration"""
        # Check if using Ollama
        if os.getenv("USE_OLLAMA", "").lower() == "true":
            return "ollama"

        # Check OpenAI API key format
        api_key = settings.openai_api_key
        if api_key.startswith("gsk_"):
            return "groq"
        elif api_key.startswith("sk-") and "openai" in api_key.lower():
            return "openai"
        elif "ollama" in api_key.lower():
            return "ollama"
        else:
            # Default to OpenAI-compatible API
            return "openai"

    async def generate_completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.3
    ) -> Dict[str, Any]:
        """
        Generate completion using the configured provider

        Returns:
            {
                "response": str,
                "tokens_used": int,
                "model": str,
                "provider": str
            }
        """
        if self.provider == "ollama":
            return await self._ollama_completion(prompt, system_prompt, max_tokens, temperature)
        else:
            return await self._openai_compatible_completion(prompt, system_prompt, max_tokens, temperature)

    async def _ollama_completion(
        self,
        prompt: str,
        system_prompt: Optional[str],
        max_tokens: int,
        temperature: float
    ) -> Dict[str, Any]:
        """Call Ollama API"""
        ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        model = os.getenv("OLLAMA_MODEL", "llama3.2")

        # Build the full prompt
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{ollama_base}/api/generate",
                    json={
                        "model": model,
                        "prompt": full_prompt,
                        "stream": False,
                        "options": {
                            "temperature": temperature,
                            "num_predict": max_tokens
                        }
                    }
                )
                response.raise_for_status()
                data = response.json()

                response_text = data.get("response", "")
                return {
                    "content": response_text,  # Use "content" for consistency
                    "response": response_text,  # Keep for backward compatibility
                    "tokens_used": data.get("eval_count", 0) + data.get("prompt_eval_count", 0),
                    "model": model,
                    "provider": "ollama",
                    "cost_usd": 0.0  # Ollama is free
                }
        except Exception as e:
            logger.error(f"Ollama API error: {e}")
            raise Exception(f"Ollama is not running. Start it with: ollama serve")

    async def _openai_compatible_completion(
        self,
        prompt: str,
        system_prompt: Optional[str],
        max_tokens: int,
        temperature: float
    ) -> Dict[str, Any]:
        """Call OpenAI-compatible API (OpenAI, Groq, Together, etc.)"""
        try:
            from openai import AsyncOpenAI

            # Get base URL (if custom provider like Groq/Together)
            base_url = os.getenv("OPENAI_API_BASE", None)

            client = AsyncOpenAI(
                api_key=settings.openai_api_key,
                base_url=base_url
            )

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature
            )

            return {
                "response": response.choices[0].message.content,
                "tokens_used": response.usage.total_tokens,
                "model": response.model,
                "provider": self.provider
            }
        except Exception as e:
            logger.error(f"LLM API error: {e}")
            raise Exception(f"LLM API failed: {str(e)}")

    def estimate_cost(self, tokens: int) -> float:
        """Estimate cost based on provider and tokens"""
        if self.provider == "ollama":
            return 0.0  # Free
        elif self.provider == "groq":
            return 0.0  # Free tier
        elif self.provider == "openai":
            # GPT-4 pricing (approximate)
            if "gpt-4" in settings.openai_model.lower():
                return (tokens / 1000) * 0.03
            else:  # GPT-3.5
                return (tokens / 1000) * 0.002
        else:
            return 0.0  # Unknown, assume free


# Singleton instance
_llm_provider = None

def get_llm_provider() -> LLMProvider:
    """Get or create LLM provider singleton"""
    global _llm_provider
    if _llm_provider is None:
        _llm_provider = LLMProvider()
    return _llm_provider