"""
Tests for the voice API endpoints.
Uses mock DB session — no real Postgres required.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from naaviq.server.auth.dependencies import get_current_user
from naaviq.server.core.database import get_db
from naaviq.server.voice.router import router

# ── App + dependency overrides ────────────────────────────────────────────────

def _build_app(current_user, db_mock) -> FastAPI:
    """Isolated FastAPI app with auth + DB overridden."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_db] = lambda: db_mock
    return app


def _make_user(org_id: str = "org-1"):
    user = MagicMock()
    user.org_id = org_id
    user.id = "user-1"
    return user


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def current_user():
    return _make_user()


@pytest.fixture
def db():
    return _make_db()


@pytest.fixture
def app(current_user, db):
    return _build_app(current_user, db)


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# ── Phone Number schemas ──────────────────────────────────────────────────────

def test_add_request_rejects_non_e164():
    from pydantic import ValidationError
    from naaviq.server.voice.schemas import AddPhoneNumberRequest
    with pytest.raises(ValidationError):
        AddPhoneNumberRequest(agent_id="a", number="0800-555-1234")


def test_add_request_rejects_invalid_provider():
    from pydantic import ValidationError
    from naaviq.server.voice.schemas import AddPhoneNumberRequest
    with pytest.raises(ValidationError):
        AddPhoneNumberRequest(agent_id="a", number="+14155551234", provider="bandwidth")


def test_add_request_accepts_valid_e164():
    from naaviq.server.voice.schemas import AddPhoneNumberRequest
    req = AddPhoneNumberRequest(agent_id="a", number="+14155551234")
    assert req.number == "+14155551234"


def test_outbound_request_rejects_non_e164():
    from pydantic import ValidationError
    from naaviq.server.voice.schemas import OutboundCallRequest
    with pytest.raises(ValidationError):
        OutboundCallRequest(agent_id="a", from_number="bad", to_number="+19995551234")


# ── GET /v1/voice/phone-numbers ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_phone_numbers_empty(client):
    with patch("naaviq.server.voice.router.VoiceService") as MockSvc:
        MockSvc.return_value.list_phone_numbers = AsyncMock(return_value=[])
        response = await client.get("/v1/voice/phone-numbers")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_phone_numbers_returns_items(client):
    from datetime import datetime, timezone

    from naaviq.server.voice.schemas import PhoneNumberResponse

    pn = PhoneNumberResponse(
        id="pn-1", org_id="org-1", agent_id="agent-1",
        number="+14155551234", provider="twilio", sid="PN-abc",
        friendly_name=None, voice_config=None, created_at=datetime.now(timezone.utc),
    )
    with patch("naaviq.server.voice.router.VoiceService") as MockSvc:
        MockSvc.return_value.list_phone_numbers = AsyncMock(return_value=[pn])
        response = await client.get("/v1/voice/phone-numbers")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["number"] == "+14155551234"


# ── POST /v1/voice/phone-numbers ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_phone_number_success(client):
    from datetime import datetime, timezone

    from naaviq.server.voice.schemas import PhoneNumberResponse

    pn = PhoneNumberResponse(
        id="pn-1", org_id="org-1", agent_id="agent-1",
        number="+14155551234", provider="twilio", sid="PN-abc",
        friendly_name=None, voice_config=None, created_at=datetime.now(timezone.utc),
    )
    with patch("naaviq.server.voice.router.VoiceService") as MockSvc:
        MockSvc.return_value.add_phone_number = AsyncMock(return_value=pn)
        response = await client.post("/v1/voice/phone-numbers", json={
            "agent_id": "agent-1",
            "number": "+14155551234",
        })
    assert response.status_code == 201
    assert response.json()["id"] == "pn-1"


@pytest.mark.asyncio
async def test_add_phone_number_409_on_duplicate(client):
    from naaviq.server.voice.exceptions import PhoneNumberAlreadyExists

    with patch("naaviq.server.voice.router.VoiceService") as MockSvc:
        MockSvc.return_value.add_phone_number = AsyncMock(
            side_effect=PhoneNumberAlreadyExists("+14155551234")
        )
        response = await client.post("/v1/voice/phone-numbers", json={
            "agent_id": "agent-1",
            "number": "+14155551234",
        })
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_add_phone_number_422_on_bad_format(client):
    response = await client.post("/v1/voice/phone-numbers", json={
        "agent_id": "agent-1",
        "number": "not-a-number",
    })
    assert response.status_code == 422


# ── DELETE /v1/voice/phone-numbers/{id} ──────────────────────────────────────

@pytest.mark.asyncio
async def test_remove_phone_number_success(client):
    with patch("naaviq.server.voice.router.VoiceService") as MockSvc:
        MockSvc.return_value.remove_phone_number = AsyncMock(return_value=None)
        response = await client.delete("/v1/voice/phone-numbers/pn-1")
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_remove_phone_number_404(client):
    from naaviq.server.voice.exceptions import PhoneNumberNotFound

    with patch("naaviq.server.voice.router.VoiceService") as MockSvc:
        MockSvc.return_value.remove_phone_number = AsyncMock(
            side_effect=PhoneNumberNotFound("pn-missing")
        )
        response = await client.delete("/v1/voice/phone-numbers/pn-missing")
    assert response.status_code == 404


# ── GET /v1/voice/calls ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_calls_empty(client):
    with patch("naaviq.server.voice.router.VoiceService") as MockSvc:
        MockSvc.return_value.list_calls = AsyncMock(return_value=[])
        response = await client.get("/v1/voice/calls")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_calls_passes_pagination(client):
    with patch("naaviq.server.voice.router.VoiceService") as MockSvc:
        MockSvc.return_value.list_calls = AsyncMock(return_value=[])
        response = await client.get("/v1/voice/calls?limit=10&offset=20")
    assert response.status_code == 200
    MockSvc.return_value.list_calls.assert_called_once_with("org-1", limit=10, offset=20)


# ── POST /v1/voice/calls/outbound ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_outbound_call_success(client):
    from naaviq.server.voice.schemas import OutboundCallResponse

    result = OutboundCallResponse(session_id="sess-1", call_sid="CA-123", status="queued")
    with patch("naaviq.server.voice.router.VoiceService") as MockSvc:
        MockSvc.return_value.initiate_outbound = AsyncMock(return_value=result)
        response = await client.post("/v1/voice/calls/outbound", json={
            "agent_id": "agent-1",
            "from_number": "+14155550000",
            "to_number": "+19995551234",
        })
    assert response.status_code == 201
    assert response.json()["call_sid"] == "CA-123"


@pytest.mark.asyncio
async def test_outbound_call_missing_twilio_creds(client):
    from naaviq.server.voice.exceptions import TwilioCredentialsMissing

    with patch("naaviq.server.voice.router.VoiceService") as MockSvc:
        MockSvc.return_value.initiate_outbound = AsyncMock(
            side_effect=TwilioCredentialsMissing()
        )
        response = await client.post("/v1/voice/calls/outbound", json={
            "agent_id": "agent-1",
            "from_number": "+14155550000",
            "to_number": "+19995551234",
        })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_outbound_call_twilio_error_returns_502(client):
    from naaviq.server.voice.exceptions import OutboundCallFailed

    with patch("naaviq.server.voice.router.VoiceService") as MockSvc:
        MockSvc.return_value.initiate_outbound = AsyncMock(
            side_effect=OutboundCallFailed("Twilio returned HTTP 503")
        )
        response = await client.post("/v1/voice/calls/outbound", json={
            "agent_id": "agent-1",
            "from_number": "+14155550000",
            "to_number": "+19995551234",
        })
    assert response.status_code == 502
