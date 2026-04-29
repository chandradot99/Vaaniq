"""
Twilio webhook security — signature verification.

Twilio signs every webhook request with HMAC-SHA1 using the auth token.
We must validate the X-Twilio-Signature header before trusting any payload.
Requests that fail validation are rejected with 403.

Docs: https://www.twilio.com/docs/usage/webhooks/webhooks-security
"""

import structlog
from fastapi import HTTPException, Request
from twilio.request_validator import RequestValidator
from naaviq.server.core.config import settings

log = structlog.get_logger()


async def verify_twilio_signature(request: Request) -> None:
    """
    FastAPI dependency — validates the X-Twilio-Signature header.

    Skipped in development (when twilio_auth_token is not configured) so
    local testing with tools like ngrok doesn't require a real Twilio account.
    """
    auth_token = settings.twilio_auth_token
    if not auth_token:
        if settings.environment == "development":
            log.warning("twilio_signature_check_skipped_no_auth_token")
            return
        raise HTTPException(status_code=500, detail="Twilio auth token not configured.")

    signature = request.headers.get("X-Twilio-Signature", "")
    url = str(request.url)

    # Twilio signs the full URL + sorted POST params
    form_data = dict(await request.form())

    validator = RequestValidator(auth_token)
    if not validator.validate(url, form_data, signature):
        log.warning("twilio_signature_invalid", url=url)
        raise HTTPException(status_code=403, detail="Invalid Twilio signature.")
