"""Integration tests for auth routes — requires PostgreSQL test database."""
from httpx import AsyncClient

REGISTER_PAYLOAD = {
    "email": "user@example.com",
    "name": "Test User",
    "password": "Password1",
    "org_name": "Acme Inc",
}


# ── Register ──────────────────────────────────────────────────────────────────

async def test_register_success(client: AsyncClient):
    response = await client.post("/v1/auth/register", json=REGISTER_PAYLOAD)
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["role"] == "owner"
    assert "org_id" in data


async def test_register_duplicate_email(client: AsyncClient):
    await client.post("/v1/auth/register", json=REGISTER_PAYLOAD)
    response = await client.post("/v1/auth/register", json=REGISTER_PAYLOAD)
    assert response.status_code == 409
    assert "already registered" in response.json()["detail"]


async def test_register_weak_password_too_short(client: AsyncClient):
    response = await client.post("/v1/auth/register", json={**REGISTER_PAYLOAD, "password": "Ab1"})
    assert response.status_code == 422


async def test_register_weak_password_no_uppercase(client: AsyncClient):
    response = await client.post("/v1/auth/register", json={**REGISTER_PAYLOAD, "password": "password1"})
    assert response.status_code == 422


async def test_register_weak_password_no_digit(client: AsyncClient):
    response = await client.post("/v1/auth/register", json={**REGISTER_PAYLOAD, "password": "Password"})
    assert response.status_code == 422


async def test_register_invalid_email(client: AsyncClient):
    response = await client.post("/v1/auth/register", json={**REGISTER_PAYLOAD, "email": "bad-email"})
    assert response.status_code == 422


# ── Login ─────────────────────────────────────────────────────────────────────

async def test_login_success(client: AsyncClient, registered_user: dict):
    response = await client.post("/v1/auth/login", json={
        "email": REGISTER_PAYLOAD["email"],
        "password": REGISTER_PAYLOAD["password"],
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["role"] == "owner"


async def test_login_wrong_password(client: AsyncClient, registered_user: dict):
    response = await client.post("/v1/auth/login", json={
        "email": REGISTER_PAYLOAD["email"],
        "password": "WrongPass1",
    })
    assert response.status_code == 401


async def test_login_unknown_email(client: AsyncClient):
    response = await client.post("/v1/auth/login", json={
        "email": "nobody@example.com",
        "password": "Password1",
    })
    assert response.status_code == 401


# ── Refresh ───────────────────────────────────────────────────────────────────

async def test_refresh_success(client: AsyncClient, registered_user: dict):
    response = await client.post("/v1/auth/refresh", json={
        "refresh_token": registered_user["refresh_token"],
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    # New refresh token must be different (rotation)
    assert data["refresh_token"] != registered_user["refresh_token"]


async def test_refresh_token_rotated(client: AsyncClient, registered_user: dict):
    """Old refresh token must not work after rotation."""
    await client.post("/v1/auth/refresh", json={"refresh_token": registered_user["refresh_token"]})
    # Try the old token again
    response = await client.post("/v1/auth/refresh", json={"refresh_token": registered_user["refresh_token"]})
    assert response.status_code == 401


async def test_refresh_invalid_token(client: AsyncClient):
    response = await client.post("/v1/auth/refresh", json={"refresh_token": "invalid-token"})
    assert response.status_code == 401


# ── Logout ────────────────────────────────────────────────────────────────────

async def test_logout_success(client: AsyncClient, registered_user: dict):
    response = await client.post("/v1/auth/logout", json={
        "refresh_token": registered_user["refresh_token"],
    })
    assert response.status_code == 204


async def test_logout_invalidates_refresh_token(client: AsyncClient, registered_user: dict):
    await client.post("/v1/auth/logout", json={"refresh_token": registered_user["refresh_token"]})
    # Token should no longer work
    response = await client.post("/v1/auth/refresh", json={"refresh_token": registered_user["refresh_token"]})
    assert response.status_code == 401


# ── Me ────────────────────────────────────────────────────────────────────────

async def test_me_success(client: AsyncClient, registered_user: dict, auth_headers: dict):
    response = await client.get("/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == REGISTER_PAYLOAD["email"]
    assert data["name"] == REGISTER_PAYLOAD["name"]
    assert data["org_name"] == REGISTER_PAYLOAD["org_name"]
    assert data["role"] == "owner"


async def test_me_no_token(client: AsyncClient):
    response = await client.get("/v1/auth/me")
    assert response.status_code == 401


async def test_me_invalid_token(client: AsyncClient):
    response = await client.get("/v1/auth/me", headers={"Authorization": "Bearer invalid.token.here"})
    assert response.status_code == 401
