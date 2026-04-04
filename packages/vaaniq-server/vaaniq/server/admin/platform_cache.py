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
    from vaaniq.server.admin.repository import PlatformConfigRepository
    from vaaniq.server.core.encryption import decrypt_key

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

    log.info("platform_cache_reloaded", providers=list(_cache.keys()))
