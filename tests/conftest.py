"""
Shared fixtures for backend-first API testing.

Requires DATABASE_URL env var. When absent, ALL tests are gracefully skipped
so CI passes with `pytest -v || true` even without DB credentials.

Uses httpx AsyncClient + ASGITransport to test FastAPI routes in-process
(no running server needed). All requests go through real /api/v1/* routes
with real JWT authentication — zero backend bypass.
"""

import os
import sys
import pytest

# ---------------------------------------------------------------------------
# Guard: skip every test when the database is unreachable
# ---------------------------------------------------------------------------
_HAS_DB = bool(os.environ.get("DATABASE_URL"))


def pytest_collection_modifyitems(config, items):
    """Auto-skip all tests when DATABASE_URL is missing."""
    if not _HAS_DB:
        marker = pytest.mark.skip(reason="DATABASE_URL not set — skipping API tests")
        for item in items:
            item.add_marker(marker)


# ---------------------------------------------------------------------------
# Fixtures (only defined when DB is available to avoid import errors)
# ---------------------------------------------------------------------------
if _HAS_DB:
    # Ensure project root is importable
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    import pytest_asyncio
    from httpx import AsyncClient, ASGITransport
    from main import app

    @pytest_asyncio.fixture
    async def client():
        """Async HTTP client wired directly to the FastAPI app."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            yield ac

    @pytest_asyncio.fixture
    async def auth_tokens(client):
        """Login with the seeded test user → (access_token, refresh_token)."""
        resp = await client.post(
            "/api/v1/login",
            data={"username": "test@gmail.com", "password": "123456"},
        )
        assert resp.status_code == 200, f"Login fixture failed: {resp.text}"
        data = resp.json()
        return data["access_token"], data["refresh_token"]

    @pytest_asyncio.fixture
    async def auth_headers(auth_tokens):
        """Ready-to-use Authorization header dict."""
        access_token, _ = auth_tokens
        return {"Authorization": f"Bearer {access_token}"}
