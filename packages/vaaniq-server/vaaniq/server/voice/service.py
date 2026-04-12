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
from vaaniq.server.agents.exceptions import AgentNotFound
from vaaniq.server.agents.repository import AgentRepository
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
        Initiate an outbound call via LiveKit CreateSIPParticipant (production path)
        or Twilio REST API fallback (when no outbound SIP trunk is configured).

        LiveKit production flow:
          1. Create session + LiveKit room (name = session_id, metadata = {session_id}).
          2. Dispatch the vaaniq-voice agent to the room — worker joins with correct metadata.
          3. LiveKit calls the user's phone via CreateSIPParticipant → outbound SIP trunk.
          4. User answers → connected to our room → agent greets them.

        This avoids the Twilio SIP header-rewriting problem where Twilio replaces
        our session_id SIP username with its own phone number, causing the worker
        to be unable to resolve the session from room metadata.

        Twilio fallback (LIVEKIT_OUTBOUND_SIP_TRUNK_ID not set):
          Uses the original Twilio REST API → TwiML → LiveKit SIP path.
          Session is resolved by phone-number lookup in the worker.
        """
        from vaaniq.server.core.config import settings as _settings

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

        # Create session row
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

        if _settings.livekit_outbound_sip_trunk_id:
            # ── LiveKit-native outbound (production) ──────────────────────────
            # Create room with session_id metadata so the worker can resolve it.
            await _create_livekit_room_with_dispatch(session_id)

            # LiveKit calls the user's phone through the outbound SIP trunk.
            sip_participant_id = await _create_sip_participant(
                room_name=session_id,
                to_number=body.to_number,
                from_number=body.from_number,
                trunk_id=_settings.livekit_outbound_sip_trunk_id,
            )

            meta = dict(session.meta)
            meta["sip_participant_id"] = sip_participant_id
            session.meta = meta
            await self.db.commit()

            log.info(
                "outbound_call_initiated",
                org_id=org_id,
                session_id=session_id,
                method="livekit_sip",
                to=body.to_number,
            )
            return OutboundCallResponse(
                session_id=session_id,
                call_sid=sip_participant_id,
                status="queued",
            )

        else:
            # ── Twilio REST API fallback ───────────────────────────────────────
            # Used when LIVEKIT_OUTBOUND_SIP_TRUNK_ID is not configured.
            # Worker resolves session_id via phone-number lookup (_find_session_by_phone).
            account_sid, auth_token = await self._get_twilio_creds(org_id)

            _platform_twilio = platform_cache.get_provider_config("twilio")
            voice_url = (
                (_platform_twilio or {}).get("webhook_url") or _settings.voice_server_url
            ).rstrip("/")

            twiml_url = f"{voice_url}/webhooks/twilio/voice/outbound?session_id={session_id}"
            status_callback = f"{voice_url}/webhooks/twilio/voice/status"

            call_sid = await _create_twilio_call(
                account_sid=account_sid,
                auth_token=auth_token,
                from_number=body.from_number,
                to_number=body.to_number,
                twiml_url=twiml_url,
                status_callback=status_callback,
            )

            meta = dict(session.meta)
            meta["call_sid"] = call_sid
            session.meta = meta
            await self.db.commit()

            log.info(
                "outbound_call_initiated",
                org_id=org_id,
                session_id=session_id,
                method="twilio_rest",
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


async def _create_livekit_room_with_dispatch(session_id: str) -> None:
    """
    Create a LiveKit room with session_id metadata and dispatch the voice agent to it.

    This is the first step of the LiveKit-native outbound flow:
      1. Pre-create the room so metadata (session_id) is set before the worker joins.
      2. Create an AgentDispatch so the worker joins immediately — it reads session_id
         from room metadata rather than relying on the SIP dispatch rule room name.
    """
    import json

    from livekit.api import (
        AgentDispatchClient,
        CreateAgentDispatchRequest,
        CreateRoomRequest,
        LiveKitAPI,
    )
    from vaaniq.server.core.config import settings

    livekit_url = settings.livekit_url
    api_key = settings.livekit_api_key
    api_secret = settings.livekit_api_secret

    if not all([livekit_url, api_key, api_secret]):
        raise RuntimeError("LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET not set")

    async with LiveKitAPI(url=livekit_url, api_key=api_key, api_secret=api_secret) as lk:
        # 1. Create room with session_id baked into metadata
        await lk.room.create_room(
            CreateRoomRequest(
                name=session_id,
                metadata=json.dumps({"session_id": session_id}),
                empty_timeout=300,
                max_participants=10,
            )
        )
        log.info("livekit_room_created", session_id=session_id)

        # 2. Dispatch the agent — worker joins the room and reads metadata immediately
        await lk.agent_dispatch.create_dispatch(
            CreateAgentDispatchRequest(
                room_name=session_id,
                agent_name="vaaniq-voice",
            )
        )
        log.info("livekit_agent_dispatched", session_id=session_id)


async def _create_sip_participant(
    *,
    room_name: str,
    to_number: str,
    from_number: str,
    trunk_id: str,
) -> str:
    """
    Use LiveKit's CreateSIPParticipant to place an outbound call to the user's phone.

    LiveKit connects the call to `room_name` via the outbound SIP trunk (Twilio).
    The user hears the agent when they answer. Returns the SIP participant identity.

    Requires LIVEKIT_OUTBOUND_SIP_TRUNK_ID to be set (Telephony → SIP trunks → Outbound
    in the LiveKit Cloud dashboard).
    """
    from livekit.api import CreateSIPParticipantRequest, LiveKitAPI
    from vaaniq.server.core.config import settings

    async with LiveKitAPI(
        url=settings.livekit_url,
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
    ) as lk:
        resp = await lk.sip.create_sip_participant(
            CreateSIPParticipantRequest(
                sip_trunk_id=trunk_id,
                sip_call_to=to_number,
                room_name=room_name,
                participant_identity=f"phone-{to_number}",
                participant_name="Caller",
                # from_number is passed as the SIP From header — determines caller ID
                # shown to the user. Must be a number registered on the SIP trunk.
                hide_phone_number=False,
            )
        )
        log.info("livekit_sip_participant_created",
                 room=room_name, to=to_number, participant=resp.participant_identity)
        return resp.participant_identity


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
