"""
Integration tests for /v1/integrations — requires PostgreSQL vaaniq_test database.
LLM provider HTTP calls are mocked via unittest.mock.
"""
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient

# ── Create ────────────────────────────────────────────────────────────────────

async def test_create_integration(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/v1/integrations",
        json={"provider": "openai", "credentials": {"api_key": "sk-test123456"}},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["provider"] == "openai"
    assert "sk-test123456" not in str(data)   # plaintext key must never appear
    assert "key_hint" in data["meta"]
    assert "sk-t" in data["meta"]["key_hint"]
    assert "····" in data["meta"]["key_hint"]


async def test_create_integration_masked_hint(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/v1/integrations",
        json={"provider": "anthropic", "credentials": {"api_key": "sk-ant-verylongkey"}},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    hint = resp.json()["meta"]["key_hint"]
    assert "sk-a" in hint
    assert "····" in hint


async def test_create_duplicate_provider_returns_409(client: AsyncClient, auth_headers: dict):
    await client.post("/v1/integrations", json={"provider": "openai", "credentials": {"api_key": "sk-abc"}}, headers=auth_headers)
    resp = await client.post("/v1/integrations", json={"provider": "openai", "credentials": {"api_key": "sk-xyz"}}, headers=auth_headers)
    assert resp.status_code == 409


async def test_create_invalid_provider_returns_422(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/v1/integrations",
        json={"provider": "nonexistent_provider", "credentials": {"api_key": "abc123"}},
        headers=auth_headers,
    )
    assert resp.status_code == 422


async def test_create_empty_credentials_returns_422(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/v1/integrations",
        json={"provider": "openai", "credentials": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 422


async def test_create_requires_auth(client: AsyncClient):
    resp = await client.post("/v1/integrations", json={"provider": "openai", "credentials": {"api_key": "sk-abc"}})
    assert resp.status_code == 401


# ── List ──────────────────────────────────────────────────────────────────────

async def test_list_integrations_empty(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/v1/integrations", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_integrations_returns_items(client: AsyncClient, auth_headers: dict):
    await client.post("/v1/integrations", json={"provider": "openai", "credentials": {"api_key": "sk-mykey999"}}, headers=auth_headers)
    await client.post("/v1/integrations", json={"provider": "anthropic", "credentials": {"api_key": "el-abc12345"}}, headers=auth_headers)

    resp = await client.get("/v1/integrations", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    providers = {k["provider"] for k in data}
    assert providers == {"openai", "anthropic"}
    # Plaintext keys must not appear anywhere in response
    full_body = str(data)
    assert "sk-mykey999" not in full_body
    assert "el-abc12345" not in full_body


# ── Delete ────────────────────────────────────────────────────────────────────

async def test_delete_integration(client: AsyncClient, auth_headers: dict):
    create = await client.post(
        "/v1/integrations", json={"provider": "openai", "credentials": {"api_key": "sk-abc"}}, headers=auth_headers
    )
    integration_id = create.json()["id"]

    resp = await client.delete(f"/v1/integrations/{integration_id}", headers=auth_headers)
    assert resp.status_code == 204

    list_resp = await client.get("/v1/integrations", headers=auth_headers)
    ids = [k["id"] for k in list_resp.json()]
    assert integration_id not in ids


async def test_delete_not_found(client: AsyncClient, auth_headers: dict):
    resp = await client.delete("/v1/integrations/nonexistent-id", headers=auth_headers)
    assert resp.status_code == 404


async def test_delete_allows_readd_same_provider(client: AsyncClient, auth_headers: dict):
    create = await client.post(
        "/v1/integrations", json={"provider": "openai", "credentials": {"api_key": "sk-old"}}, headers=auth_headers
    )
    integration_id = create.json()["id"]
    await client.delete(f"/v1/integrations/{integration_id}", headers=auth_headers)

    resp = await client.post(
        "/v1/integrations", json={"provider": "openai", "credentials": {"api_key": "sk-new"}}, headers=auth_headers
    )
    assert resp.status_code == 201


# ── Test endpoint ─────────────────────────────────────────────────────────────

async def test_test_endpoint_openai_valid_key(client: AsyncClient, auth_headers: dict):
    create = await client.post(
        "/v1/integrations", json={"provider": "openai", "credentials": {"api_key": "sk-real"}}, headers=auth_headers
    )
    integration_id = create.json()["id"]

    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("vaaniq.server.integrations.service.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client.return_value)
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.return_value.get = AsyncMock(return_value=mock_response)

        resp = await client.post(f"/v1/integrations/{integration_id}/test", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["tested"] is True
    assert data["error"] is None


async def test_test_endpoint_openai_invalid_key(client: AsyncClient, auth_headers: dict):
    create = await client.post(
        "/v1/integrations", json={"provider": "openai", "credentials": {"api_key": "sk-bad"}}, headers=auth_headers
    )
    integration_id = create.json()["id"]

    mock_response = MagicMock()
    mock_response.status_code = 401

    with patch("vaaniq.server.integrations.service.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client.return_value)
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.return_value.get = AsyncMock(return_value=mock_response)

        resp = await client.post(f"/v1/integrations/{integration_id}/test", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False
    assert data["tested"] is True
    assert "401" in data["error"]


async def test_test_endpoint_untestable_provider(client: AsyncClient, auth_headers: dict):
    # deepgram is a valid provider but not in TESTABLE_PROVIDERS
    create = await client.post(
        "/v1/integrations", json={"provider": "deepgram", "credentials": {"api_key": "dg-abc123"}}, headers=auth_headers
    )
    integration_id = create.json()["id"]

    resp = await client.post(f"/v1/integrations/{integration_id}/test", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["tested"] is False


async def test_test_endpoint_updates_last_tested_at(client: AsyncClient, auth_headers: dict):
    create = await client.post(
        "/v1/integrations", json={"provider": "openai", "credentials": {"api_key": "sk-test"}}, headers=auth_headers
    )
    integration_id = create.json()["id"]
    assert create.json()["meta"].get("last_tested_at") is None

    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("vaaniq.server.integrations.service.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client.return_value)
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.return_value.get = AsyncMock(return_value=mock_response)

        await client.post(f"/v1/integrations/{integration_id}/test", headers=auth_headers)

    list_resp = await client.get("/v1/integrations", headers=auth_headers)
    item = next(k for k in list_resp.json() if k["id"] == integration_id)
    assert item["meta"].get("last_tested_at") is not None


# ── Cross-org isolation ───────────────────────────────────────────────────────

async def test_cannot_access_other_orgs_integration(client: AsyncClient, auth_headers: dict):
    create = await client.post(
        "/v1/integrations", json={"provider": "openai", "credentials": {"api_key": "sk-org1"}}, headers=auth_headers
    )
    integration_id = create.json()["id"]

    reg2 = await client.post("/v1/auth/register", json={
        "email": "other@example.com",
        "name": "Other User",
        "password": "Password1",
        "org_name": "Other Org",
    })
    headers2 = {"Authorization": f"Bearer {reg2.json()['access_token']}"}

    assert (await client.delete(f"/v1/integrations/{integration_id}", headers=headers2)).status_code == 404
    assert (await client.post(f"/v1/integrations/{integration_id}/test", headers=headers2)).status_code == 404
