"""
Business logic for voice API endpoints.

Phone number management: add, list, reassign, remove numbers for an org.
Call management: list voice sessions, initiate outbound calls via Twilio REST API.
"""

import uuid
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vaaniq.server.admin import platform_cache
from vaaniq.server.agents.repository import AgentRepository
from vaaniq.server.agents.exceptions import AgentNotFound
from vaaniq.server.core.encryption import decrypt_key
from vaaniq.server.integrations.repository import IntegrationRepository
from vaaniq.server.models.session import Session, SessionStatus
from vaaniq.server.voice.exceptions import (
    OutboundCallFailed,
    PhoneNumberAccessDenied,
    PhoneNumberAlreadyExists,
    PhoneNumberNotFound,
    TwilioCredentialsMissing,
)
from vaaniq.server.voice.models import PhoneNumber
from vaaniq.server.voice.repository import PhoneNumberRepository
from vaaniq.server.voice.schemas import (
    AddPhoneNumberRequest,
    CallResponse,
    OutboundCallRequest,
    OutboundCallResponse,
    PhoneNumberResponse,
    ReassignPhoneNumberRequest,
    TwilioAvailableNumber,
    UpdateVoiceConfigRequest,
    VoiceConfig,
)
from vaaniq.voice.transport.twiml import outbound_connect_twiml

log = structlog.get_logger()


def _to_phone_response(pn: PhoneNumber) -> PhoneNumberResponse:
    vc = pn.voice_config
    return PhoneNumberResponse(
        id=pn.id,
        org_id=pn.org_id,
        agent_id=pn.agent_id,
        number=pn.number,
        provider=pn.provider,
        sid=pn.sid,
        friendly_name=pn.friendly_name,
        voice_config=VoiceConfig(**vc) if vc else None,
        created_at=pn.created_at,
    )


def _to_call_response(session: Session) -> CallResponse:
    return CallResponse(
        id=session.id,
        org_id=session.org_id,
        agent_id=session.agent_id,
        channel=session.channel,
        user_id=session.user_id,
        status=session.status,
        duration_seconds=session.duration_seconds,
        sentiment=session.sentiment,
        summary=session.summary,
        meta=session.meta or {},
        created_at=session.created_at,
        ended_at=session.ended_at,
    )


class VoiceService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._phone_repo = PhoneNumberRepository(db)
        self._agent_repo = AgentRepository(db)
        self._integration_repo = IntegrationRepository(db)

    # ── Phone Numbers ─────────────────────────────────────────────────────────

    async def list_phone_numbers(
        self, org_id: str, agent_id: str | None = None
    ) -> list[PhoneNumberResponse]:
        if agent_id:
            numbers = await self._phone_repo.list_by_agent(agent_id)
            # Ensure numbers belong to this org
            numbers = [pn for pn in numbers if pn.org_id == org_id]
        else:
            numbers = await self._phone_repo.list_by_org(org_id)
        return [_to_phone_response(pn) for pn in numbers]

    async def add_phone_number(
        self, org_id: str, body: AddPhoneNumberRequest
    ) -> PhoneNumberResponse:
        # Validate agent belongs to org
        agent = await self._agent_repo.get_by_id(body.agent_id)
        if not agent or agent.deleted_at is not None:
            raise AgentNotFound()
        if agent.org_id != org_id:
            raise PhoneNumberAccessDenied()

        # Reject if number already registered (active)
        existing = await self._phone_repo.get_by_number(body.number)
        if existing:
            raise PhoneNumberAlreadyExists(body.number)

        pn = await self._phone_repo.create(
            org_id=org_id,
            agent_id=body.agent_id,
            number=body.number,
            provider=body.provider,
            sid=body.sid,
            friendly_name=body.friendly_name,
        )
        await self.db.commit()
        log.info("phone_number_added", org_id=org_id, number=body.number, agent_id=body.agent_id)
        return _to_phone_response(pn)

    async def reassign_phone_number(
        self, org_id: str, number_id: str, body: ReassignPhoneNumberRequest
    ) -> PhoneNumberResponse:
        pn = await self._get_own_number(org_id, number_id)

        # Validate new agent belongs to same org
        agent = await self._agent_repo.get_by_id(body.agent_id)
        if not agent or agent.deleted_at is not None:
            raise AgentNotFound()
        if agent.org_id != org_id:
            raise PhoneNumberAccessDenied()

        await self._phone_repo.reassign(number_id, body.agent_id)
        await self.db.commit()
        pn.agent_id = body.agent_id  # reflect the change
        log.info("phone_number_reassigned", number_id=number_id, new_agent=body.agent_id)
        return _to_phone_response(pn)

    async def remove_phone_number(self, org_id: str, number_id: str) -> None:
        await self._get_own_number(org_id, number_id)
        await self._phone_repo.soft_delete(number_id)
        await self.db.commit()
        log.info("phone_number_removed", org_id=org_id, number_id=number_id)

    async def update_voice_config(
        self, org_id: str, number_id: str, body: UpdateVoiceConfigRequest
    ) -> PhoneNumberResponse:
        pn = await self._get_own_number(org_id, number_id)
        vc_dict = None
        if body.voice_config is not None:
            vc_dict = {k: v for k, v in body.voice_config.model_dump().items() if v is not None}
        await self._phone_repo.update_voice_config(number_id, vc_dict)
        await self.db.commit()
        await self.db.refresh(pn)
        log.info("phone_number_voice_config_updated", org_id=org_id, number_id=number_id)
        return _to_phone_response(pn)

    async def _get_own_number(self, org_id: str, number_id: str) -> PhoneNumber:
        result = await self.db.execute(
            select(PhoneNumber).where(
                PhoneNumber.id == number_id,
                PhoneNumber.deleted_at.is_(None),
            )
        )
        pn = result.scalar_one_or_none()
        if not pn:
            raise PhoneNumberNotFound(number_id)
        if pn.org_id != org_id:
            raise PhoneNumberAccessDenied()
        return pn

    # ── Calls ─────────────────────────────────────────────────────────────────

    async def list_calls(
        self, org_id: str, limit: int = 50, offset: int = 0
    ) -> list[CallResponse]:
        result = await self.db.execute(
            select(Session)
            .where(Session.org_id == org_id, Session.channel == "voice")
            .order_by(Session.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        sessions = result.scalars().all()
        return [_to_call_response(s) for s in sessions]

    async def initiate_outbound(
        self, org_id: str, body: OutboundCallRequest
    ) -> OutboundCallResponse:
        """
        Initiate an outbound call via Twilio REST API.

        Flow:
          1. Validate agent and from_number belong to org.
          2. Fetch org's Twilio credentials from integrations (BYOK).
          3. Create a session row so context_builder can find it.
          4. Call Twilio REST API — Twilio opens a fresh WebSocket to our webhook.
        """
        # Validate agent
        agent = await self._agent_repo.get_by_id(body.agent_id)
        if not agent or agent.deleted_at is not None:
            raise AgentNotFound()
        if agent.org_id != org_id:
            raise PhoneNumberAccessDenied()

        # Validate from_number belongs to this org
        pn = await self._phone_repo.get_by_number(body.from_number)
        if not pn or pn.org_id != org_id:
            raise PhoneNumberNotFound(body.from_number)

        # Fetch Twilio credentials from org integrations
        account_sid, auth_token = await self._get_twilio_creds(org_id)

        # Create session row (status active, call_sid filled in after Twilio responds)
        session_id = str(uuid.uuid4())
        session = Session(
            id=session_id,
            org_id=org_id,
            agent_id=body.agent_id,
            channel="voice",
            user_id=body.to_number,
            status=SessionStatus.active,
            meta={
                "direction": "outbound",
                "from": body.from_number,
                "to": body.to_number,
                "extra_context": body.extra_context,
            },
        )
        self.db.add(session)
        await self.db.flush()

        # Resolve public backend URL — platform_cache takes precedence over settings
        from vaaniq.server.core.config import settings as _settings
        _platform_twilio = platform_cache.get_provider_config("twilio")
        backend_url = (
            (_platform_twilio or {}).get("webhook_url") or _settings.backend_url
        ).rstrip("/")

        # Build the TwiML URL Twilio will fetch when the call connects
        twiml_url = f"{backend_url}/webhooks/twilio/voice/outbound?session_id={session_id}"
        status_callback = f"{backend_url}/webhooks/twilio/voice/status"

        # Initiate via Twilio REST API
        call_sid = await _create_twilio_call(
            account_sid=account_sid,
            auth_token=auth_token,
            from_number=body.from_number,
            to_number=body.to_number,
            twiml_url=twiml_url,
            status_callback=status_callback,
        )

        # Store call_sid so context_builder / status webhook can look it up
        meta = dict(session.meta)
        meta["call_sid"] = call_sid
        session.meta = meta
        await self.db.commit()

        log.info(
            "outbound_call_initiated",
            org_id=org_id,
            session_id=session_id,
            call_sid=call_sid,
            to=body.to_number,
        )
        return OutboundCallResponse(
            session_id=session_id,
            call_sid=call_sid,
            status="queued",
        )

    async def list_twilio_numbers(self, org_id: str) -> list[TwilioAvailableNumber]:
        """
        Fetch all purchased numbers from the org's Twilio account and mark
        which ones are already imported as pipelines.
        """
        import httpx

        account_sid, auth_token = await self._get_twilio_creds(org_id)

        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/IncomingPhoneNumbers.json"
        params = {"PageSize": "100"}

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url, params=params, auth=(account_sid, auth_token))

        if response.status_code != 200:
            log.error(
                "twilio_list_numbers_failed",
                status=response.status_code,
                body=response.text[:300],
            )
            raise OutboundCallFailed(
                f"Twilio returned HTTP {response.status_code}: {response.text[:200]}"
            )

        # Build set of already-imported numbers for O(1) lookup
        existing = await self._phone_repo.list_by_org(org_id)
        imported_numbers = {pn.number for pn in existing}

        results = []
        for item in response.json().get("incoming_phone_numbers", []):
            cap = item.get("capabilities", {})
            results.append(TwilioAvailableNumber(
                number=item["phone_number"],
                sid=item["sid"],
                friendly_name=item.get("friendly_name"),
                capabilities={
                    "voice": cap.get("voice", False),
                    "sms": cap.get("sms", False),
                    "mms": cap.get("mms", False),
                },
                already_imported=item["phone_number"] in imported_numbers,
            ))

        return results

    async def _get_twilio_creds(self, org_id: str) -> tuple[str, str]:
        """
        Return (account_sid, auth_token) for the org's Twilio integration.
        Falls back to platform-level Twilio credentials if org has none.
        """
        import json as _json

        integration = await self._integration_repo.get_by_provider(org_id, "twilio")
        if integration and integration.credentials:
            raw = decrypt_key(integration.credentials)
            creds = _json.loads(raw)
            return creds.get("account_sid", ""), creds.get("auth_token", "")

        # Fall back to platform-level credentials (set via Platform Settings admin page)
        platform_twilio = platform_cache.get_provider_config("twilio")
        if platform_twilio and platform_twilio.get("auth_token"):
            return platform_twilio.get("account_sid", ""), platform_twilio["auth_token"]

        raise TwilioCredentialsMissing()


async def _create_twilio_call(
    *,
    account_sid: str,
    auth_token: str,
    from_number: str,
    to_number: str,
    twiml_url: str,
    status_callback: str,
) -> str:
    """
    Call Twilio REST API to create an outbound call.
    Returns the Twilio CallSid.
    """
    import httpx

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls.json"
    payload = {
        "From": from_number,
        "To": to_number,
        "Url": twiml_url,
        "StatusCallback": status_callback,
        "StatusCallbackMethod": "POST",
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(url, data=payload, auth=(account_sid, auth_token))

        if response.status_code not in (200, 201):
            log.error(
                "twilio_call_failed",
                status=response.status_code,
                body=response.text[:500],
            )
            raise OutboundCallFailed(
                f"Twilio returned HTTP {response.status_code}: {response.text[:200]}"
            )

        return response.json()["sid"]

    except OutboundCallFailed:
        raise
    except Exception as exc:
        log.exception("twilio_call_error")
        raise OutboundCallFailed(f"Failed to reach Twilio: {exc}") from exc
