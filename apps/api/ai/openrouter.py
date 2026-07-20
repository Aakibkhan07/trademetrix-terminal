import json
import logging

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "google/gemini-2.0-flash-001"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.gemini_api_key}",
        "Content-Type": "application/json",
    }


async def chat_completion(prompt: str, model: str = DEFAULT_MODEL) -> str | None:
    if not settings.gemini_api_key:
        logger.warning("GEMINI_API_KEY not set — AI features unavailable")
        return None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{OPENROUTER_API_BASE}/chat/completions",
                headers=_headers(),
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error("OpenRouter API call failed: %s", e, exc_info=True)
        return None
