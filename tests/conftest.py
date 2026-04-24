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
import uuid
import time
import pytest

# ---------------------------------------------------------------------------
# Performance thresholds (seconds) — generous for cold-start / free-tier DBs
# ---------------------------------------------------------------------------
PERF_THRESHOLD_FAST = 2.0       # simple reads (list, status)
PERF_THRESHOLD_STANDARD = 5.0   # writes + auth (create, login)
PERF_THRESHOLD_HEAVY = 10.0     # multi-step (orders, predictions)

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


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Warn loudly when ALL tests were skipped — no real validation ran."""
    stats = terminalreporter.stats
    passed = len(stats.get("passed", []))
    failed = len(stats.get("failed", []))
    skipped = len(stats.get("skipped", []))

    if skipped > 0 and passed == 0 and failed == 0:
        terminalreporter.section("SKIP WARNING", sep="!", yellow=True)
        terminalreporter.write_line(
            "WARNING: All tests skipped — no real validation executed.",
            yellow=True,
        )
        terminalreporter.write_line(
            "Set DATABASE_URL to run tests against the backend.",
            yellow=True,
        )


# ---------------------------------------------------------------------------
# Unique-ID generator (collision-proof across parallel / repeated runs)
# ---------------------------------------------------------------------------
def uid() -> str:
    """Short UUID segment for unique SKUs, phones, and names."""
    return uuid.uuid4().hex[:10]


def assert_response_time(start: float, threshold: float, label: str = ""):
    """Assert that elapsed time since `start` is within `threshold` seconds."""
    elapsed = time.time() - start
    assert elapsed < threshold, (
        f"Performance violation{f' ({label})' if label else ''}: "
        f"{elapsed:.2f}s > {threshold:.1f}s threshold"
    )
    return elapsed


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
        """Ready-to-use Authorization header dict. Login happens once per test."""
        access_token, _ = auth_tokens
        return {"Authorization": f"Bearer {access_token}"}

    # ------------------------------------------------------------------
    # Shared test-data helpers (used by product / order / flow tests)
    # ------------------------------------------------------------------
    @pytest_asyncio.fixture
    async def temp_product(client, auth_headers):
        """Create a temporary product, yield (id, selling_price), then soft-delete."""
        sku = f"TMP-{uid()}"
        resp = await client.post("/api/v1/products/", json={
            "name": f"TempProduct {sku}",
            "sku": sku,
            "category": "AutoTest",
            "cost_price": 10.0,
            "selling_price": 30.0,
            "lead_time_days": 3,
        }, headers=auth_headers)
        assert resp.status_code == 200, f"temp_product fixture failed: {resp.text}"
        data = resp.json()
        yield data["id"], data["selling_price"]
        # Cleanup — soft-delete
        await client.delete(f"/api/v1/products/{data['id']}", headers=auth_headers)

    @pytest_asyncio.fixture
    async def temp_contact(client, auth_headers):
        """Create a temporary contact, yield its id, then soft-delete."""
        tag = uid()
        resp = await client.post("/api/v1/contacts", json={
            "name": f"TestContact {tag}",
            "phone": f"999{tag}",
            "type": "supplier",
        }, headers=auth_headers)
        assert resp.status_code == 200, f"temp_contact fixture failed: {resp.text}"
        cid = resp.json()["id"]
        yield cid
        await client.delete(f"/api/v1/contacts/{cid}", headers=auth_headers)
