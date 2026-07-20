import json
import logging

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "google/gemini-2.5-flash"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.gemini_api_key}",
        "Content-Type": "application/json",
    }


async def chat_completion(prompt: str, model: str = DEFAULT_MODEL, max_tokens: int = 2000) -> str | None:
    if not settings.gemini_api_key:
        logger.warning("GEMINI_API_KEY not set — AI features unavailable")
        return None
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{OPENROUTER_API_BASE}/chat/completions",
                headers=_headers(),
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error("OpenRouter API call failed: %s", e, exc_info=True)
        return None
