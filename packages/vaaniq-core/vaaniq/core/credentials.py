"""CredentialStore — abstract interface for org credential access.

vaaniq-core defines the interface only — no external dependencies, no storage logic.

Implementations live in:
    vaaniq-tools   → EnvCredentialStore   (env vars, for standalone dev use)
    vaaniq-server  → PostgresCredentialStore (encrypted DB, multi-tenant)

Any node, tool, or graph component that needs credentials should accept a
CredentialStore instance — never import a concrete implementation directly.
"""
from abc import ABC, abstractmethod


class CredentialStore(ABC):
    """Abstract credential store.

    Returns org_keys — a dict injected into every graph node and tool at runtime.

    Shape of org_keys:
        Simple providers (llm, stt, tts):
            org_keys["openai"]    = "sk-..."         # plain string
            org_keys["deepgram"]  = "sk-..."

        Complex providers (app, infrastructure):
            org_keys["google"]    = {"client_id": "...", "refresh_token": "...", ...}
            org_keys["pinecone"]  = {"api_key": "...", "environment": "...", "index_name": "..."}
    """

    @abstractmethod
    async def get_org_keys(self, org_id: str) -> dict:
        """Return decrypted credentials for org_id as a flat {provider: value} dict."""
        ...
