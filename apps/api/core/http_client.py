import asyncio
from typing import Optional

import httpx


class SharedHttpClient:
    _instance: Optional["SharedHttpClient"] = None
    _client: httpx.AsyncClient | None = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            async with self._lock:
                if self._client is None or self._client.is_closed:
                    self._client = httpx.AsyncClient(
                        timeout=httpx.Timeout(30.0, connect=10.0),
                        limits=httpx.Limits(
                            max_connections=100,
                            max_keepalive_connections=20,
                            keepalive_expiry=30.0,
                        ),
                        headers={"User-Agent": "TradeMetrix/0.1.0"},
                    )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


shared_http = SharedHttpClient()


async def get_http_client() -> httpx.AsyncClient:
    return await shared_http.get_client()
