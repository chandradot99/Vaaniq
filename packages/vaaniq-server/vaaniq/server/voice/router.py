"""
Voice API endpoints.

Phone numbers: manage which Twilio numbers route to which agents.
Calls: list call history, initiate outbound calls.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from vaaniq.server.agents.exceptions import AgentNotFound
from vaaniq.server.auth.dependencies import CurrentUser, get_current_user
from vaaniq.server.core.database import get_db
from vaaniq.server.voice.exceptions import (
    OutboundCallFailed,
    PhoneNumberAccessDenied,
    PhoneNumberAlreadyExists,
    PhoneNumberNotFound,
    TwilioCredentialsMissing,
)
from vaaniq.server.voice.schemas import (
    AddPhoneNumberRequest,
    CallResponse,
    OutboundCallRequest,
    OutboundCallResponse,
    PhoneNumberResponse,
    ReassignPhoneNumberRequest,
    TwilioAvailableNumber,
    UpdateVoiceConfigRequest,
)
from vaaniq.server.voice.service import VoiceService

router = APIRouter(prefix="/v1/voice", tags=["voice"])


# ── Phone Numbers ─────────────────────────────────────────────────────────────

@router.get("/twilio/numbers", response_model=list[TwilioAvailableNumber])
async def list_twilio_numbers(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TwilioAvailableNumber]:
    """
    Fetch all purchased phone numbers from the org's Twilio account.
    Already-imported numbers are marked with already_imported=true.
    Used by the frontend number picker — no manual E.164 entry needed.
    """
    try:
        return await VoiceService(db).list_twilio_numbers(current.org_id)
    except TwilioCredentialsMissing:
        raise HTTPException(
            status_code=422,
            detail="Twilio credentials not configured. Add a Twilio integration first.",
        )
    except OutboundCallFailed as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/phone-numbers", response_model=list[PhoneNumberResponse])
async def list_phone_numbers(
    agent_id: str | None = Query(default=None),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PhoneNumberResponse]:
    return await VoiceService(db).list_phone_numbers(current.org_id, agent_id=agent_id)


@router.post(
    "/phone-numbers",
    response_model=PhoneNumberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_phone_number(
    body: AddPhoneNumberRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PhoneNumberResponse:
    try:
        return await VoiceService(db).add_phone_number(current.org_id, body)
    except AgentNotFound:
        raise HTTPException(status_code=404, detail="Agent not found")
    except PhoneNumberAccessDenied:
        raise HTTPException(status_code=403, detail="Agent belongs to a different org")
    except PhoneNumberAlreadyExists as exc:
        raise HTTPException(
            status_code=409, detail=f"Phone number already registered: {exc.number}"
        )


@router.patch("/phone-numbers/{number_id}", response_model=PhoneNumberResponse)
async def reassign_phone_number(
    number_id: str,
    body: ReassignPhoneNumberRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PhoneNumberResponse:
    try:
        return await VoiceService(db).reassign_phone_number(current.org_id, number_id, body)
    except PhoneNumberNotFound:
        raise HTTPException(status_code=404, detail="Phone number not found")
    except PhoneNumberAccessDenied:
        raise HTTPException(status_code=403, detail="Forbidden")
    except AgentNotFound:
        raise HTTPException(status_code=404, detail="Target agent not found")


@router.patch("/phone-numbers/{number_id}/config", response_model=PhoneNumberResponse)
async def update_voice_config(
    number_id: str,
    body: UpdateVoiceConfigRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PhoneNumberResponse:
    try:
        return await VoiceService(db).update_voice_config(current.org_id, number_id, body)
    except PhoneNumberNotFound:
        raise HTTPException(status_code=404, detail="Phone number not found")
    except PhoneNumberAccessDenied:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.delete("/phone-numbers/{number_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_phone_number(
    number_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await VoiceService(db).remove_phone_number(current.org_id, number_id)
    except PhoneNumberNotFound:
        raise HTTPException(status_code=404, detail="Phone number not found")
    except PhoneNumberAccessDenied:
        raise HTTPException(status_code=403, detail="Forbidden")


# ── Calls ─────────────────────────────────────────────────────────────────────

@router.get("/calls", response_model=list[CallResponse])
async def list_calls(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CallResponse]:
    return await VoiceService(db).list_calls(current.org_id, limit=limit, offset=offset)


@router.post(
    "/calls/outbound",
    response_model=OutboundCallResponse,
    status_code=status.HTTP_201_CREATED,
)
async def initiate_outbound_call(
    body: OutboundCallRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OutboundCallResponse:
    try:
        return await VoiceService(db).initiate_outbound(current.org_id, body)
    except AgentNotFound:
        raise HTTPException(status_code=404, detail="Agent not found")
    except PhoneNumberNotFound:
        raise HTTPException(
            status_code=404,
            detail="from_number is not registered to this org",
        )
    except PhoneNumberAccessDenied:
        raise HTTPException(status_code=403, detail="Forbidden")
    except TwilioCredentialsMissing:
        raise HTTPException(
            status_code=422,
            detail="Twilio credentials not configured. Add a Twilio integration first.",
        )
    except OutboundCallFailed as exc:
        raise HTTPException(status_code=502, detail=str(exc))
