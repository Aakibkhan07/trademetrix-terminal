import asyncio
from typing import AsyncGenerator, Generator

import pytest
from pytest_asyncio import fixture as async_fixture

from core.config import settings


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@async_fixture
async def client() -> AsyncGenerator:
    from httpx import ASGITransport, AsyncClient
    from main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@async_fixture
async def auth_headers(client) -> dict:
    signup_resp = await client.post("/api/v1/auth/signup", json={
        "email": "test@example.com",
        "password": "TestPass123!",
    })
    if signup_resp.status_code == 409:
        signin_resp = await client.post("/api/v1/auth/signin", json={
            "email": "test@example.com",
            "password": "TestPass123!",
        })
        token = signin_resp.json().get("access_token", "")
    else:
        token = signup_resp.json().get("access_token", "")

    return {"Authorization": f"Bearer {token}"}
