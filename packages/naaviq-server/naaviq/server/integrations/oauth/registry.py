"""OAUTH_REGISTRY — maps provider names to their OAuthProvider implementations.

To add a new OAuth provider:
  1. Create oauth/providers/<name>.py with a class that extends OAuthProvider
  2. Add an entry here: OAUTH_REGISTRY["<name>"] = YourProvider()
  3. Add the required env vars to .env.example with setup instructions
  The router and all other code require no changes.
"""
from naaviq.server.integrations.oauth.base import OAuthProvider
from naaviq.server.integrations.oauth.providers.google import GoogleOAuthProvider

OAUTH_REGISTRY: dict[str, OAuthProvider] = {
    "google": GoogleOAuthProvider(),
    # "slack":    SlackOAuthProvider(),     ← future
    # "hubspot":  HubSpotOAuthProvider(),   ← future
    # "notion":   NotionOAuthProvider(),    ← future
    # "github":   GitHubOAuthProvider(),    ← future
}
