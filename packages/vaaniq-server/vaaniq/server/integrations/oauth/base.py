"""Shared utilities and abstract base class for OAuth provider implementations.

State token flow
----------------
The state parameter passed to the provider's authorization URL is a short-lived
signed JWT that encodes org_id + provider + optional code_verifier (for PKCE).
This prevents CSRF and ties the callback back to the right org without any
server-side session storage.

PKCE flow (required by Google and most modern providers)
---------------------------------------------------------
1. Router generates a PKCE pair: (code_verifier, code_challenge)
2. code_verifier is stored in the state JWT (encrypted, expires in 10 min)
3. code_challenge is passed to get_auth_url() → included in authorization URL
4. Provider receives code_challenge in the auth request
5. On callback, code_verifier is extracted from state JWT
6. exchange_code(code, code_verifier) sends it to the token endpoint
7. Provider verifies challenge == SHA256(verifier) — proves same client
"""
import hashlib
import secrets
import base64
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from jose import jwt, JWTError

from vaaniq.server.core.config import settings

_STATE_ALGORITHM = "HS256"
_STATE_TTL_MINUTES = 10


def generate_pkce_pair() -> tuple[str, str]:
    """Generate a PKCE code_verifier and code_challenge (S256 method).

    Returns (code_verifier, code_challenge).
    code_verifier is stored in the state JWT.
    code_challenge is passed to the provider's authorization URL.
    """
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return code_verifier, code_challenge


def create_state_token(org_id: str, provider: str, code_verifier: str = "") -> str:
    """Create a short-lived signed JWT for the OAuth state parameter.

    code_verifier is included when the provider requires PKCE (e.g. Google).
    """
    now = datetime.now(timezone.utc)
    payload = {
        "org_id": org_id,
        "provider": provider,
        "cv": code_verifier,   # cv = code_verifier (short to keep JWT compact)
        "iat": now,
        "exp": now + timedelta(minutes=_STATE_TTL_MINUTES),
    }
    return jwt.encode(payload, settings.fernet_key, algorithm=_STATE_ALGORITHM)


def verify_state_token(state: str) -> tuple[str, str, str]:
    """Verify state JWT and return (org_id, provider, code_verifier).

    code_verifier is empty string for providers that don't use PKCE.
    Raises ValueError on invalid or expired state.
    """
    try:
        payload = jwt.decode(state, settings.fernet_key, algorithms=[_STATE_ALGORITHM])
        return payload["org_id"], payload["provider"], payload.get("cv", "")
    except (JWTError, KeyError) as e:
        raise ValueError(f"Invalid OAuth state: {e}") from e


class OAuthProvider(ABC):
    """Abstract base class for all OAuth provider implementations.

    Adding a new OAuth provider requires only:
      1. Subclass OAuthProvider in oauth/providers/<name>.py
      2. Register the instance in oauth/registry.py
      3. Document the required env vars in .env.example
      The oauth router never changes.

    Design rules:
    - is_configured() must be cheap (env var check, no I/O)
    - get_auth_url() must be synchronous (no network calls)
    - exchange_code() and get_account_info() are async (network calls)
    - credentials dict returned by exchange_code() is what gets encrypted and
      stored in the integrations table — it must contain everything needed to
      rebuild the provider's SDK credentials object later
    - use_pkce = True means the router will generate a PKCE pair and pass
      code_challenge to get_auth_url() and code_verifier to exchange_code()
    """

    use_pkce: bool = False  # override to True in providers that require PKCE

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Matches the key in OAUTH_REGISTRY and the provider column in integrations."""
        ...

    @abstractmethod
    def is_configured(self) -> bool:
        """True if all required env vars are present.

        Used by the frontend to show "Connect" vs "Setup required" state.
        Should never raise — return False on any missing config.
        """
        ...

    @abstractmethod
    def get_auth_url(self, state: str, code_challenge: str = "") -> str:
        """Return the provider's authorization URL including the state parameter.

        code_challenge is provided when use_pkce = True. Providers that don't
        use PKCE can ignore it.
        """
        ...

    @abstractmethod
    async def exchange_code(self, code: str, code_verifier: str = "") -> dict:
        """Exchange the authorization code for tokens.

        code_verifier is provided when use_pkce = True.
        Returns a credentials dict that will be JSON-encoded, encrypted, and
        stored in the integrations table. Include everything needed to refresh
        the access token later (client_id, client_secret, refresh_token, token_uri).
        """
        ...

    @abstractmethod
    async def get_account_info(self, credentials: dict) -> dict:
        """Fetch human-readable account info after a successful token exchange.

        Returns a meta dict stored alongside the integration (e.g. account_email,
        workspace_name). Should never raise — return {} on failure.
        """
        ...
