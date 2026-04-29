"""
Voice API endpoints.

Phone numbers: manage which Twilio numbers route to which agents.
Calls: list call history, initiate outbound calls.
Providers: list registered STT/TTS providers, models, and voices.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

import naaviq.voice.providers  # noqa: F401 — ensures all providers are registered
from naaviq.server.agents.exceptions import AgentNotFound
from naaviq.server.auth.dependencies import CurrentUser, get_current_user
from naaviq.server.core.database import get_db
from naaviq.server.voice.exceptions import (
    OutboundCallFailed,
    PhoneNumberAccessDenied,
    PhoneNumberAlreadyExists,
    PhoneNumberNameConflict,
    PhoneNumberNotFound,
    TwilioCredentialsMissing,
)
from naaviq.server.voice.providers_service import (
    _resolve_api_key,
    get_stt_models,
    get_tts_models,
    get_tts_voices,
)
from naaviq.server.voice.schemas import (
    AddPhoneNumberRequest,
    CallResponse,
    ModelInfoResponse,
    OutboundCallRequest,
    OutboundCallResponse,
    PhoneNumberResponse,
    ReassignPhoneNumberRequest,
    STTProviderResponse,
    TTSPreviewRequest,
    TTSProviderResponse,
    TwilioAvailableNumber,
    UpdatePhoneNumberNameRequest,
    UpdateVoiceConfigRequest,
    VoiceInfoResponse,
)
from naaviq.server.voice.service import VoiceService
from naaviq.voice.exceptions import ProviderNotFoundError
from naaviq.voice.providers.registry import ProviderRegistry

router = APIRouter(prefix="/v1/voice", tags=["voice"])


# ── Voice Providers ───────────────────────────────────────────────────────────

@router.get("/providers/stt", response_model=list[STTProviderResponse])
async def list_stt_providers(
    current: CurrentUser = Depends(get_current_user),
) -> list[STTProviderResponse]:
    """List all registered STT providers."""
    return [
        STTProviderResponse(
            provider_id=provider_id,
            display_name=cls.display_name,
            languages=cls.languages,
        )
        for provider_id, cls in ProviderRegistry.all_stt().items()
    ]


@router.get("/providers/stt/{provider}/models", response_model=list[ModelInfoResponse])
async def list_stt_models(
    provider: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ModelInfoResponse]:
    """List available STT models for the given provider."""
    try:
        models = await get_stt_models(provider, current.org_id, db)
    except ProviderNotFoundError:
        raise HTTPException(status_code=404, detail=f"STT provider '{provider}' not found")
    return [
        ModelInfoResponse(
            id=m.id,
            display_name=m.display_name,
            description=m.description,
            languages=m.languages,
            is_default=m.is_default,
            streaming=m.streaming,
            category=m.category,
        )
        for m in models
    ]


@router.get("/providers/tts", response_model=list[TTSProviderResponse])
async def list_tts_providers(
    current: CurrentUser = Depends(get_current_user),
) -> list[TTSProviderResponse]:
    """List all registered TTS providers."""
    return [
        TTSProviderResponse(
            provider_id=provider_id,
            display_name=cls.display_name,
            supports_voices=cls.supports_voices(),
            languages=cls.languages,
        )
        for provider_id, cls in ProviderRegistry.all_tts().items()
    ]


@router.get("/providers/tts/{provider}/models", response_model=list[ModelInfoResponse])
async def list_tts_models(
    provider: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ModelInfoResponse]:
    """List available TTS models for the given provider."""
    try:
        models = await get_tts_models(provider, current.org_id, db)
    except ProviderNotFoundError:
        raise HTTPException(status_code=404, detail=f"TTS provider '{provider}' not found")
    return [
        ModelInfoResponse(
            id=m.id,
            display_name=m.display_name,
            description=m.description,
            languages=m.languages,
            is_default=m.is_default,
            streaming=m.streaming,
            category=m.category,
        )
        for m in models
    ]


@router.get("/providers/tts/{provider}/voices", response_model=list[VoiceInfoResponse])
async def list_tts_voices(
    provider: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[VoiceInfoResponse]:
    """List available TTS voices for the given provider."""
    try:
        voices = await get_tts_voices(provider, current.org_id, db)
    except ProviderNotFoundError:
        raise HTTPException(status_code=404, detail=f"TTS provider '{provider}' not found")
    return [
        VoiceInfoResponse(
            id=v.id,
            name=v.name,
            preview_url=v.preview_url,
            gender=v.gender,
            language=v.language,
            category=v.category,
            description=v.description,
        )
        for v in voices
    ]


# ── TTS Preview ───────────────────────────────────────────────────────────────

@router.post("/preview/tts")
async def preview_tts(
    body: TTSPreviewRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Synthesise a short TTS preview using the given provider and voice config.
    Returns raw audio bytes (audio/mpeg).
    """
    try:
        provider_cls = ProviderRegistry.get_tts(body.tts_provider)
    except ProviderNotFoundError:
        raise HTTPException(status_code=404, detail=f"TTS provider '{body.tts_provider}' not found")

    api_key = await _resolve_api_key(body.tts_provider, current.org_id, db)
    if not api_key:
        raise HTTPException(
            status_code=422,
            detail=f"No API key configured for provider '{body.tts_provider}'. Add an integration first.",
        )

    config = body.voice_config.model_dump() if body.voice_config else {}
    result = await provider_cls.synthesize_preview(body.text, config, api_key)

    if result is None:
        raise HTTPException(status_code=501, detail="Preview not supported by this provider")

    audio_bytes, mime_type = result
    return Response(content=audio_bytes, media_type=mime_type)


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


@router.get("/phone-numbers/{number_id}", response_model=PhoneNumberResponse)
async def get_phone_number(
    number_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PhoneNumberResponse:
    try:
        return await VoiceService(db).get_phone_number(current.org_id, number_id)
    except PhoneNumberNotFound:
        raise HTTPException(status_code=404, detail="Phone number not found")
    except PhoneNumberAccessDenied:
        raise HTTPException(status_code=403, detail="Forbidden")


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


@router.patch("/phone-numbers/{number_id}/name", response_model=PhoneNumberResponse)
async def update_phone_number_name(
    number_id: str,
    body: UpdatePhoneNumberNameRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PhoneNumberResponse:
    try:
        return await VoiceService(db).update_phone_number_name(current.org_id, number_id, body)
    except PhoneNumberNotFound:
        raise HTTPException(status_code=404, detail="Phone number not found")
    except PhoneNumberAccessDenied:
        raise HTTPException(status_code=403, detail="Forbidden")
    except PhoneNumberNameConflict as exc:
        raise HTTPException(status_code=409, detail=f"A pipeline named '{exc.name}' already exists in this org")


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
