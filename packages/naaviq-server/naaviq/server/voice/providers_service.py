"""
Voice provider service — fetches and caches models and voices from provider APIs.

Resolution order for the API key:
  1. Org's own integration (BYOK)
  2. Platform-level default (platform_configs)
  3. None — returns static list without an API call

Caching: in-process TTL dict.
  - Models: 24h TTL (rarely change)
  - Voices: 1h TTL (user can add custom voices in ElevenLabs/Cartesia)
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from naaviq.server.admin import platform_cache
from naaviq.server.integrations.service import PostgresCredentialStore
from naaviq.voice.providers import ProviderRegistry
from naaviq.voice.providers.base import ModelInfo, VoiceInfo

log = structlog.get_logger()

_MODELS_TTL = 86_400.0   # 24 hours
_VOICES_TTL = 3_600.0    # 1 hour


# ── Simple in-process TTL cache ───────────────────────────────────────────────

@dataclass
class _CacheEntry:
    value: object
    expires_at: float


_cache: dict[str, _CacheEntry] = {}


def _get(key: str) -> object | None:
    entry = _cache.get(key)
    if entry and time.monotonic() < entry.expires_at:
        return entry.value
    return None


def _set(key: str, value: object, ttl: float) -> None:
    _cache[key] = _CacheEntry(value=value, expires_at=time.monotonic() + ttl)


# ── Key resolution ────────────────────────────────────────────────────────────

async def _resolve_api_key(
    provider: str,
    org_id: str,
    db: AsyncSession,
) -> str | None:
    """
    Return the best available API key for `provider`:
      1. Org's own BYOK integration
      2. Platform-level default
      3. None
    """
    org_keys = await PostgresCredentialStore(db).get_org_keys(org_id)
    key = org_keys.get(provider)
    if key:
        if isinstance(key, dict):
            key = key.get("api_key")
        if key:
            return str(key)

    platform = platform_cache.get_provider_config(provider)
    if platform:
        return platform.get("api_key") or platform.get("credentials", {}).get("api_key")

    return None


# ── Public service functions ──────────────────────────────────────────────────

async def get_stt_models(
    provider: str,
    org_id: str,
    db: AsyncSession,
) -> list[ModelInfo]:
    """
    Return STT models for the given provider.
    Uses live API if a key is available; falls back to static list.
    """
    cache_key = f"stt_models:{provider}"
    cached = _get(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    provider_cls = ProviderRegistry.get_stt(provider)

    api_key = await _resolve_api_key(provider, org_id, db)
    if api_key:
        models = await provider_cls.fetch_models(api_key)
    else:
        log.info("stt_models_no_key_using_static", provider=provider, org_id=org_id)
        models = provider_cls.static_models()

    _set(cache_key, models, _MODELS_TTL)
    return models


async def get_tts_models(
    provider: str,
    org_id: str,
    db: AsyncSession,
) -> list[ModelInfo]:
    """
    Return TTS models for the given provider.
    Uses live API if a key is available; falls back to static list.
    """
    cache_key = f"tts_models:{provider}"
    cached = _get(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    provider_cls = ProviderRegistry.get_tts(provider)

    api_key = await _resolve_api_key(provider, org_id, db)
    if api_key:
        models = await provider_cls.fetch_models(api_key)
    else:
        log.info("tts_models_no_key_using_static", provider=provider, org_id=org_id)
        models = provider_cls.static_models()

    _set(cache_key, models, _MODELS_TTL)
    return models


async def get_tts_voices(
    provider: str,
    org_id: str,
    db: AsyncSession,
) -> list[VoiceInfo]:
    """
    Return TTS voices for the given provider.
    Uses live API if a key is available; falls back to static list.
    Voices are keyed per org (custom voices differ per account).
    """
    provider_cls = ProviderRegistry.get_tts(provider)

    if not provider_cls.supports_voices():
        return []

    cache_key = f"tts_voices:{provider}:{org_id}"
    cached = _get(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    api_key = await _resolve_api_key(provider, org_id, db)
    if api_key:
        voices = await provider_cls.fetch_voices(api_key)
    else:
        log.info("tts_voices_no_key_using_static", provider=provider, org_id=org_id)
        voices = provider_cls.static_voices()

    _set(cache_key, voices, _VOICES_TTL)
    return voices
