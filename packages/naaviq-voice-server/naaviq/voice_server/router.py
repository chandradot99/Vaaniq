"""
Combined webhook router for naaviq-voice-server.

Aggregates all telephony provider routers (Twilio, Telnyx, Vonage) and the
LiveKit room webhook into a single FastAPI APIRouter that main.py includes.

Adding a new telephony provider:
    1. Create routers/<provider>.py with the webhook handlers
    2. Import and include the router here
"""

from fastapi import APIRouter

from naaviq.voice_server.routers.livekit import router as livekit_router
from naaviq.voice_server.routers.telnyx import router as telnyx_router
from naaviq.voice_server.routers.twilio import router as twilio_router
from naaviq.voice_server.routers.vonage import router as vonage_router

# Single combined router — main.py does app.include_router(router)
router = APIRouter()
router.include_router(twilio_router)
router.include_router(telnyx_router)
router.include_router(vonage_router)
router.include_router(livekit_router)
