"""
Authentication endpoint tests.

Covers: login, token validation, refresh rotation, logout/revocation.
All tests use real /api/v1/* routes with real JWT flow.
"""

import pytest


async def test_login_valid_credentials(client):
    """Valid login returns access + refresh tokens."""
    resp = await client.post(
        "/api/v1/login",
        data={"username": "test@gmail.com", "password": "123456"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


async def test_login_invalid_credentials(client):
    """Bad credentials return 401."""
    resp = await client.post(
        "/api/v1/login",
        data={"username": "wrong@email.com", "password": "badpass"},
    )
    assert resp.status_code == 401
    assert "Incorrect credentials" in resp.json()["detail"]


async def test_me_with_valid_token(client, auth_headers):
    """/me returns user info for authenticated request."""
    resp = await client.get("/api/v1/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["user"]["email"] == "test@gmail.com"


async def test_me_without_token(client):
    """/me rejects unauthenticated requests."""
    resp = await client.get("/api/v1/me")
    assert resp.status_code == 401


async def test_me_with_forged_token(client):
    """/me rejects an invalid JWT."""
    resp = await client.get(
        "/api/v1/me",
        headers={"Authorization": "Bearer forged_token_xyz_123"},
    )
    assert resp.status_code == 401


async def test_token_refresh_rotation(client):
    """Refresh endpoint rotates both tokens."""
    # Login first
    login = await client.post(
        "/api/v1/login",
        data={"username": "test@gmail.com", "password": "123456"},
    )
    tokens = login.json()

    # Refresh
    resp = await client.post(
        "/api/v1/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert resp.status_code == 200
    new = resp.json()
    assert "access_token" in new
    assert "refresh_token" in new
    assert new["access_token"] != tokens["access_token"]


async def test_logout_revokes_token(client):
    """After logout the access token is revoked via token_version."""
    # Login
    login = await client.post(
        "/api/v1/login",
        data={"username": "test@gmail.com", "password": "123456"},
    )
    tokens = login.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    # Logout
    resp = await client.post("/api/v1/logout", headers=headers)
    assert resp.status_code == 200

    # Old token should now be dead
    check = await client.get("/api/v1/me", headers=headers)
    assert check.status_code == 401
