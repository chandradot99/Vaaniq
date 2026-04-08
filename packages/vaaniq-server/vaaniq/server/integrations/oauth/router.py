"""Generic OAuth router — handles any provider registered in OAUTH_REGISTRY.

Two endpoints serve all current and future OAuth integrations:

  GET /v1/integrations/oauth/{provider}/connect
      Authenticated. Returns the authorization URL for the given provider.
      Frontend redirects the user's browser to that URL.

  GET /v1/integrations/oauth/{provider}/callback
      Unauthenticated (browser redirect from provider). Exchanges the
      authorization code for tokens, stores them, and redirects the user
      back to the frontend integrations page.

To add a new OAuth provider: see oauth/registry.py. This file never changes.
"""
import json
import traceback

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from vaaniq.server.auth.dependencies import CurrentUser, get_current_user
from vaaniq.server.core.config import settings
from vaaniq.server.core.database import get_db
from vaaniq.server.core.encryption import encrypt_key
from vaaniq.server.integrations.oauth.base import (
    create_state_token,
    generate_pkce_pair,
    verify_state_token,
)
from vaaniq.server.integrations.oauth.registry import OAUTH_REGISTRY
from vaaniq.server.integrations.repository import IntegrationRepository
from vaaniq.server.integrations.schemas import OAuthConnectUrlResponse

oauth_router = APIRouter(prefix="/oauth", tags=["integrations:oauth"])


@oauth_router.get("/{provider}/connect", response_model=OAuthConnectUrlResponse)
async def oauth_connect_url(
    provider: str,
    current: CurrentUser = Depends(get_current_user),
) -> OAuthConnectUrlResponse:
    """Return the OAuth authorization URL for the requested provider.

    The frontend should redirect window.location to this URL.
    Raises 404 if the provider is unknown, 501 if it is not configured
    (i.e. the required env vars are missing on this deployment).
    """
    oauth_provider = OAUTH_REGISTRY.get(provider)
    if not oauth_provider:
        raise HTTPException(status_code=404, detail=f"OAuth provider '{provider}' not supported")
    if not oauth_provider.is_configured():
        raise HTTPException(
            status_code=501,
            detail=(
                f"{provider.capitalize()} OAuth is not configured on this server. "
                f"Set the required environment variables — see .env.example for instructions."
            ),
        )

    code_verifier, code_challenge = generate_pkce_pair() if oauth_provider.use_pkce else ("", "")
    state = create_state_token(current.org_id, provider, code_verifier)
    url = oauth_provider.get_auth_url(state, code_challenge)
    return OAuthConnectUrlResponse(url=url)


@oauth_router.get("/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: str = "",
    state: str = "",
    error: str = "",
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Handle OAuth callback from the provider.

    Verifies the state JWT, exchanges the code for tokens, upserts the
    integration record, and redirects the user back to the frontend.
    All failure paths redirect with a query-string error code so the
    frontend can display a toast — never a raw HTTP error (the browser
    would show a blank page instead of going back to the app).
    """
    frontend_base = f"{settings.frontend_url}/integrations"
    oauth_provider = OAUTH_REGISTRY.get(provider)

    if not oauth_provider:
        return RedirectResponse(f"{frontend_base}?error=unknown_provider")

    if error or not code or not state:
        return RedirectResponse(f"{frontend_base}?error={provider}_oauth_denied")

    try:
        org_id, state_provider, code_verifier = verify_state_token(state)
        if state_provider != provider:
            raise ValueError("provider mismatch in state token")
    except ValueError:
        return RedirectResponse(f"{frontend_base}?error=invalid_state")

    try:
        credentials = await oauth_provider.exchange_code(code, code_verifier)
        meta = await oauth_provider.get_account_info(credentials)
    except Exception as exc:
        print(f"[oauth:{provider}] token_exchange_failed: {exc}\n{traceback.format_exc()}")
        return RedirectResponse(f"{frontend_base}?error=token_exchange_failed")

    repo = IntegrationRepository(db)
    encrypted = encrypt_key(json.dumps(credentials))
    existing = await repo.get_by_provider(org_id, provider)

    if existing:
        await repo.update(existing.id, credentials=encrypted, status="connected", meta=meta)
    else:
        integration = await repo.create(
            org_id=org_id,
            provider=provider,
            category="app",
            display_name=provider.capitalize(),
            credentials=encrypted,
            config={},
        )
        await repo.update(integration.id, meta=meta)

    await db.commit()
    return RedirectResponse(f"{frontend_base}?connected={provider}")
