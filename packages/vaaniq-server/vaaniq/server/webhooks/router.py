"""
Twilio webhook router — voice routes have moved to vaaniq-voice-server.

This file is intentionally empty. All /webhooks/twilio/voice/* endpoints
now live in packages/vaaniq-voice-server/vaaniq/voice_server/router.py
and are served by the standalone voice server process (port 8001 locally,
Fly.io iad in production).

Keeping this module so vaaniq-server/main.py doesn't need restructuring;
the empty router is a no-op.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
