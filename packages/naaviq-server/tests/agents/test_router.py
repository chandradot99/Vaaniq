"""
Integration tests for /v1/agents — requires PostgreSQL naaviq_test database.
"""
from httpx import AsyncClient

# ── Create ────────────────────────────────────────────────────────────────────

async def test_create_agent_simple_mode(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/v1/agents", json={"name": "Support Bot"}, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Support Bot"
    assert data["simple_mode"] is True
    assert data["graph_config"] is not None
    assert data["graph_config"]["entry_point"] == "start"


async def test_create_agent_with_system_prompt(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/v1/agents",
        json={"name": "Sales Bot", "system_prompt": "You help users buy products."},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    start_config = data["graph_config"]["nodes"][0]["config"]
    assert start_config["system_message"] == "You help users buy products."


async def test_create_agent_invalid_language(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/v1/agents",
        json={"name": "Bot", "language": "xyz"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


async def test_create_agent_empty_name(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/v1/agents", json={"name": "  "}, headers=auth_headers)
    assert resp.status_code == 422


async def test_create_agent_requires_auth(client: AsyncClient):
    resp = await client.post("/v1/agents", json={"name": "Bot"})
    assert resp.status_code == 401


# ── List ──────────────────────────────────────────────────────────────────────

async def test_list_agents_empty(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/v1/agents", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_agents_returns_own_org_only(client: AsyncClient, auth_headers: dict):
    await client.post("/v1/agents", json={"name": "Bot 1"}, headers=auth_headers)
    await client.post("/v1/agents", json={"name": "Bot 2"}, headers=auth_headers)

    resp = await client.get("/v1/agents", headers=auth_headers)
    assert resp.status_code == 200
    names = [a["name"] for a in resp.json()]
    assert "Bot 1" in names
    assert "Bot 2" in names
    assert len(names) == 2


# ── Get ───────────────────────────────────────────────────────────────────────

async def test_get_agent(client: AsyncClient, auth_headers: dict):
    create = await client.post("/v1/agents", json={"name": "My Bot"}, headers=auth_headers)
    agent_id = create.json()["id"]

    resp = await client.get(f"/v1/agents/{agent_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == agent_id


async def test_get_agent_not_found(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/v1/agents/nonexistent-id", headers=auth_headers)
    assert resp.status_code == 404


# ── Update ────────────────────────────────────────────────────────────────────

async def test_update_agent_name(client: AsyncClient, auth_headers: dict):
    create = await client.post("/v1/agents", json={"name": "Old Name"}, headers=auth_headers)
    agent_id = create.json()["id"]

    resp = await client.patch(
        f"/v1/agents/{agent_id}",
        json={"name": "New Name"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"


async def test_update_system_prompt_regenerates_graph(client: AsyncClient, auth_headers: dict):
    create = await client.post(
        "/v1/agents",
        json={"name": "Bot", "system_prompt": "Hello"},
        headers=auth_headers,
    )
    agent_id = create.json()["id"]

    resp = await client.patch(
        f"/v1/agents/{agent_id}",
        json={"system_prompt": "Updated prompt"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    start_config = resp.json()["graph_config"]["nodes"][0]["config"]
    assert start_config["system_message"] == "Updated prompt"


# ── Update graph ──────────────────────────────────────────────────────────────

async def test_update_graph_sets_advanced_mode(client: AsyncClient, auth_headers: dict):
    create = await client.post("/v1/agents", json={"name": "Bot"}, headers=auth_headers)
    agent_id = create.json()["id"]

    custom_graph = {
        "entry_point": "greet",
        "nodes": [
            {"id": "greet", "type": "end_session", "config": {"farewell_message": "Hi!"}}
        ],
        "edges": [{"id": "e1", "source": "greet", "target": "end"}],
    }
    resp = await client.put(
        f"/v1/agents/{agent_id}/graph",
        json={"graph_config": custom_graph},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["simple_mode"] is False
    assert data["graph_config"]["entry_point"] == "greet"


async def test_update_graph_missing_entry_point(client: AsyncClient, auth_headers: dict):
    create = await client.post("/v1/agents", json={"name": "Bot"}, headers=auth_headers)
    agent_id = create.json()["id"]

    resp = await client.put(
        f"/v1/agents/{agent_id}/graph",
        json={"graph_config": {"nodes": []}},
        headers=auth_headers,
    )
    assert resp.status_code == 422


# ── Delete ────────────────────────────────────────────────────────────────────

async def test_delete_agent(client: AsyncClient, auth_headers: dict):
    create = await client.post("/v1/agents", json={"name": "To Delete"}, headers=auth_headers)
    agent_id = create.json()["id"]

    resp = await client.delete(f"/v1/agents/{agent_id}", headers=auth_headers)
    assert resp.status_code == 204

    # Should no longer appear in list
    list_resp = await client.get("/v1/agents", headers=auth_headers)
    ids = [a["id"] for a in list_resp.json()]
    assert agent_id not in ids


async def test_delete_agent_not_found(client: AsyncClient, auth_headers: dict):
    resp = await client.delete("/v1/agents/nonexistent-id", headers=auth_headers)
    assert resp.status_code == 404
