"""In-memory cache for platform configs.

Loaded at startup and refreshed after every admin upsert/delete.
Providers read from this cache instead of env vars.

Security: decrypted credentials live in memory the same way env vars do.
"""
import json

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()

# provider → merged dict of config (non-secrets) + decrypted credentials (secrets)
_cache: dict[str, dict] = {}


def get_provider_config(provider: str) -> dict | None:
    """Return merged config+credentials for a provider, or None if not configured."""
    return _cache.get(provider) or None


async def reload(db: AsyncSession) -> None:
    """Reload all enabled platform configs from DB into the in-memory cache."""
    from naaviq.server.admin.repository import PlatformConfigRepository
    from naaviq.server.core.encryption import decrypt_key

    _cache.clear()
    configs = await PlatformConfigRepository(db).list_all()
    for pc in configs:
        if not pc.enabled:
            continue
        try:
            creds = json.loads(decrypt_key(pc.credentials)) if pc.credentials and pc.credentials != "{}" else {}
        except Exception:
            creds = {}
        _cache[pc.provider] = {**(pc.config or {}), **creds}

    # Push LangSmith config from DB to os.environ so LangChain picks it up.
    # DB config takes precedence over .env values set earlier in setup_observability().
    langsmith = _cache.get("langsmith")
    if langsmith and langsmith.get("api_key"):
        import os
        os.environ["LANGSMITH_API_KEY"] = langsmith["api_key"]
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGSMITH_PROJECT"] = langsmith.get("project", "naaviq")
        os.environ["LANGSMITH_ENDPOINT"] = langsmith.get("endpoint", "https://api.smith.langchain.com")
        log.info("langsmith_configured_from_db", project=langsmith.get("project", "naaviq"))

    log.info("platform_cache_reloaded", providers=list(_cache.keys()))
