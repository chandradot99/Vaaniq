"""
Twilio webhook router — voice routes have moved to naaviq-voice-server.

This file is intentionally empty. All /webhooks/twilio/voice/* endpoints
now live in packages/naaviq-voice-server/naaviq/voice_server/router.py
and are served by the standalone voice server process (port 8001 locally,
Fly.io iad in production).

Keeping this module so naaviq-server/main.py doesn't need restructuring;
the empty router is a no-op.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
