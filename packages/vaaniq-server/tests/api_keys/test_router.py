"""
Integration tests for /v1/api-keys — requires PostgreSQL vaaniq_test database.
LLM provider HTTP calls are mocked via unittest.mock.
"""
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient

# ── Create ────────────────────────────────────────────────────────────────────

async def test_create_api_key(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/v1/api-keys",
        json={"service": "openai", "key": "sk-test123456"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["service"] == "openai"
    assert "sk-test123456" not in str(data)   # plaintext key must never appear
    assert "key_hint" in data
    assert data["key_hint"].startswith("sk-")
    assert "****" in data["key_hint"]


async def test_create_api_key_masked_hint(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/v1/api-keys",
        json={"service": "anthropic", "key": "sk-ant-verylongkey"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    hint = resp.json()["key_hint"]
    assert hint == "sk-****...ey"


async def test_create_duplicate_service_returns_409(client: AsyncClient, auth_headers: dict):
    await client.post("/v1/api-keys", json={"service": "openai", "key": "sk-abc"}, headers=auth_headers)
    resp = await client.post("/v1/api-keys", json={"service": "openai", "key": "sk-xyz"}, headers=auth_headers)
    assert resp.status_code == 409


async def test_create_invalid_service_returns_422(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/v1/api-keys",
        json={"service": "nonexistent_provider", "key": "abc123"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


async def test_create_empty_key_returns_422(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/v1/api-keys",
        json={"service": "openai", "key": "  "},
        headers=auth_headers,
    )
    assert resp.status_code == 422


async def test_create_requires_auth(client: AsyncClient):
    resp = await client.post("/v1/api-keys", json={"service": "openai", "key": "sk-abc"})
    assert resp.status_code == 401


# ── List ──────────────────────────────────────────────────────────────────────

async def test_list_api_keys_empty(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/v1/api-keys", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_api_keys_returns_masked(client: AsyncClient, auth_headers: dict):
    await client.post("/v1/api-keys", json={"service": "openai", "key": "sk-mykey999"}, headers=auth_headers)
    await client.post("/v1/api-keys", json={"service": "elevenlabs", "key": "el-abc12345"}, headers=auth_headers)

    resp = await client.get("/v1/api-keys", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    services = {k["service"] for k in data}
    assert services == {"openai", "elevenlabs"}
    # Plaintext keys must not appear
    full_body = str(data)
    assert "sk-mykey999" not in full_body
    assert "el-abc12345" not in full_body


# ── Delete ────────────────────────────────────────────────────────────────────

async def test_delete_api_key(client: AsyncClient, auth_headers: dict):
    create = await client.post(
        "/v1/api-keys", json={"service": "openai", "key": "sk-abc"}, headers=auth_headers
    )
    key_id = create.json()["id"]

    resp = await client.delete(f"/v1/api-keys/{key_id}", headers=auth_headers)
    assert resp.status_code == 204

    # Should no longer appear in list
    list_resp = await client.get("/v1/api-keys", headers=auth_headers)
    ids = [k["id"] for k in list_resp.json()]
    assert key_id not in ids


async def test_delete_not_found(client: AsyncClient, auth_headers: dict):
    resp = await client.delete("/v1/api-keys/nonexistent-id", headers=auth_headers)
    assert resp.status_code == 404


async def test_delete_allows_readd_same_service(client: AsyncClient, auth_headers: dict):
    create = await client.post(
        "/v1/api-keys", json={"service": "openai", "key": "sk-old"}, headers=auth_headers
    )
    key_id = create.json()["id"]
    await client.delete(f"/v1/api-keys/{key_id}", headers=auth_headers)

    # Re-add same service after delete — should succeed
    resp = await client.post(
        "/v1/api-keys", json={"service": "openai", "key": "sk-new"}, headers=auth_headers
    )
    assert resp.status_code == 201


# ── Test endpoint ─────────────────────────────────────────────────────────────

async def test_test_endpoint_openai_valid_key(client: AsyncClient, auth_headers: dict):
    create = await client.post(
        "/v1/api-keys", json={"service": "openai", "key": "sk-real"}, headers=auth_headers
    )
    key_id = create.json()["id"]

    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("vaaniq.server.api_keys.service.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client.return_value)
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.return_value.get = AsyncMock(return_value=mock_response)

        resp = await client.post(f"/v1/api-keys/{key_id}/test", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["tested"] is True
    assert data["error"] is None


async def test_test_endpoint_openai_invalid_key(client: AsyncClient, auth_headers: dict):
    create = await client.post(
        "/v1/api-keys", json={"service": "openai", "key": "sk-bad"}, headers=auth_headers
    )
    key_id = create.json()["id"]

    mock_response = MagicMock()
    mock_response.status_code = 401

    with patch("vaaniq.server.api_keys.service.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client.return_value)
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.return_value.get = AsyncMock(return_value=mock_response)

        resp = await client.post(f"/v1/api-keys/{key_id}/test", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False
    assert data["tested"] is True
    assert "401" in data["error"]


async def test_test_endpoint_unsupported_provider(client: AsyncClient, auth_headers: dict):
    create = await client.post(
        "/v1/api-keys", json={"service": "twilio", "key": "AC-abc123"}, headers=auth_headers
    )
    key_id = create.json()["id"]

    resp = await client.post(f"/v1/api-keys/{key_id}/test", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["tested"] is False


async def test_test_endpoint_updates_last_tested_at(client: AsyncClient, auth_headers: dict):
    create = await client.post(
        "/v1/api-keys", json={"service": "openai", "key": "sk-test"}, headers=auth_headers
    )
    key_id = create.json()["id"]
    assert create.json()["last_tested_at"] is None

    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("vaaniq.server.api_keys.service.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client.return_value)
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.return_value.get = AsyncMock(return_value=mock_response)

        await client.post(f"/v1/api-keys/{key_id}/test", headers=auth_headers)

    # Verify last_tested_at is now set
    list_resp = await client.get("/v1/api-keys", headers=auth_headers)
    key_data = next(k for k in list_resp.json() if k["id"] == key_id)
    assert key_data["last_tested_at"] is not None


# ── Cross-org isolation ───────────────────────────────────────────────────────

async def test_cannot_access_other_orgs_key(client: AsyncClient, auth_headers: dict):
    # Create a key as user 1
    create = await client.post(
        "/v1/api-keys", json={"service": "openai", "key": "sk-org1"}, headers=auth_headers
    )
    key_id = create.json()["id"]

    # Register a second user (different org)
    reg2 = await client.post("/v1/auth/register", json={
        "email": "other@example.com",
        "name": "Other User",
        "password": "Password1",
        "org_name": "Other Org",
    })
    headers2 = {"Authorization": f"Bearer {reg2.json()['access_token']}"}

    # Second user cannot delete or test first user's key
    assert (await client.delete(f"/v1/api-keys/{key_id}", headers=headers2)).status_code == 404
    assert (await client.post(f"/v1/api-keys/{key_id}/test", headers=headers2)).status_code == 404
