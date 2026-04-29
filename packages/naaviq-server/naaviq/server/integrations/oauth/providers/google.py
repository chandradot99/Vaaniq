"""Google OAuth provider implementation.

Self-hosted setup (one-time per deployment)
-------------------------------------------
1. Go to https://console.cloud.google.com → APIs & Services → Credentials
2. Click "Create Credentials" → "OAuth 2.0 Client ID" → Application type: Web application
3. Under "Authorized redirect URIs" add:
       https://your-domain.com/v1/integrations/oauth/google/callback
   (For local dev: http://localhost:8000/v1/integrations/oauth/google/callback)
4. Enable these APIs in the Google Cloud Console:
       - Google Calendar API
       - Gmail API
       - Google People API (for userinfo)
5. Set in your .env:
       GOOGLE_OAUTH_CLIENT_ID=<your client_id>
       GOOGLE_OAUTH_CLIENT_SECRET=<your client_secret>
       GOOGLE_OAUTH_REDIRECT_URI=https://your-domain.com/v1/integrations/oauth/google/callback

Cloud version: Naaviq operates its own registered Google OAuth app — self-hosters
must register their own because OAuth requires pre-registered redirect URIs.
"""
import asyncio

import httpx
from google_auth_oauthlib.flow import Flow
from naaviq.server.admin.platform_cache import get_provider_config
from naaviq.server.core.config import settings
from naaviq.server.integrations.oauth.base import OAuthProvider

_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/spreadsheets",
]


class GoogleOAuthProvider(OAuthProvider):

    use_pkce = True  # Google requires PKCE for web OAuth apps

    @property
    def provider_name(self) -> str:
        return "google"

    def _google_config(self) -> dict:
        """Return Google OAuth credentials from platform_cache (DB) or env vars fallback."""
        cached = get_provider_config("google")
        if cached and cached.get("client_id") and cached.get("client_secret"):
            return cached
        return {
            "client_id": settings.google_oauth_client_id,
            "client_secret": settings.google_oauth_client_secret,
            "redirect_uri": settings.google_oauth_redirect_uri,
        }

    def is_configured(self) -> bool:
        cfg = self._google_config()
        return bool(cfg.get("client_id") and cfg.get("client_secret"))

    def _client_config(self) -> dict:
        cfg = self._google_config()
        return {
            "web": {
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
                "redirect_uris": [cfg.get("redirect_uri", settings.google_oauth_redirect_uri)],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }

    def get_auth_url(self, state: str, code_challenge: str = "") -> str:
        redirect_uri = self._google_config().get("redirect_uri", settings.google_oauth_redirect_uri)
        flow = Flow.from_client_config(
            self._client_config(),
            scopes=_SCOPES,
            redirect_uri=redirect_uri,
        )
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",  # always prompt to guarantee a refresh_token
            state=state,
            code_challenge=code_challenge,
            code_challenge_method="S256",
        )
        return auth_url

    async def exchange_code(self, code: str, code_verifier: str = "") -> dict:
        def _fetch() -> dict:
            cfg = self._google_config()
            redirect_uri = cfg.get("redirect_uri", settings.google_oauth_redirect_uri)
            flow = Flow.from_client_config(
                self._client_config(),
                scopes=_SCOPES,
                redirect_uri=redirect_uri,
            )
            flow.fetch_token(code=code, code_verifier=code_verifier)
            creds = flow.credentials
            return {
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
                "access_token": creds.token,
                "refresh_token": creds.refresh_token,
                "token_uri": "https://oauth2.googleapis.com/token",
            }

        return await asyncio.to_thread(_fetch)

    async def get_account_info(self, credentials: dict) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {credentials['access_token']}"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {"account_email": data.get("email", "")}
        except Exception:
            pass
        return {}
