"""Google OAuth2 credentials helper.

org_keys["google"] is a dict with at minimum:
    client_id, client_secret, refresh_token

Optionally also has access_token (used as initial token; auto-refreshed when expired).
"""
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials


def build_google_credentials(org_keys: dict) -> Credentials:
    """Build and auto-refresh Google OAuth2 credentials from org_keys."""
    google = org_keys.get("google")
    if not google:
        raise ValueError(
            "Google integration not configured. "
            "Add it under Settings → Integrations."
        )

    creds = Credentials(
        token=google.get("access_token"),
        refresh_token=google["refresh_token"],
        client_id=google["client_id"],
        client_secret=google["client_secret"],
        token_uri="https://oauth2.googleapis.com/token",
    )

    # Refresh if no token or expired
    if not creds.valid:
        creds.refresh(Request())

    return creds
