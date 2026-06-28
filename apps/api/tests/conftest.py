import asyncio
from collections.abc import AsyncGenerator, Generator
from datetime import UTC

import pytest
from pytest_asyncio import fixture as async_fixture


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


_SESSION_AUTH: dict | None = None


@async_fixture(scope="session")
async def auth_headers() -> dict:
    global _SESSION_AUTH
    if _SESSION_AUTH is not None:
        return _SESSION_AUTH

    import subprocess
    import uuid
    from datetime import datetime

    from core.security import create_access_token

    user_id = str(uuid.uuid4())
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S+00")
    email = f"ses_{user_id[:8]}@test.example.com"

    try:
        subprocess.run(
            [
                "psql",
                "-h", "127.0.0.1", "-p", "54322",
                "-U", "postgres", "-d", "postgres",
                "-c",
                f"""
                INSERT INTO auth.users (id, email, encrypted_password, email_confirmed_at, created_at, updated_at, raw_app_meta_data, raw_user_meta_data, role)
                VALUES ('{user_id}', '{email}', '', '{now}', '{now}', '{now}', '{{}}', '{{}}', 'authenticated')
                ON CONFLICT (id) DO NOTHING;

                INSERT INTO public.profiles (id, email, full_name, subscription_tier, created_at, updated_at)
                VALUES ('{user_id}', '{email}', 'Test User', 'free', '{now}', '{now}')
                ON CONFLICT (id) DO NOTHING;
                """
            ],
            env={**__import__("os").environ, "PGPASSWORD": "postgres"},
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        pass

    token = create_access_token(subject=user_id)
    _SESSION_AUTH = {"Authorization": f"Bearer {token}"}
    return _SESSION_AUTH
