"""
ProviderRegistry — central lookup for all registered STT and TTS providers.

Providers register themselves via the class decorators:

    @ProviderRegistry.register_stt
    class DeepgramSTTProvider(STTProviderBase): ...

    @ProviderRegistry.register_tts
    class CartesiaTTSProvider(TTSProviderBase): ...

The registry is then used by the factory functions in stt/__init__.py and
tts/__init__.py to look up and instantiate the correct provider at call time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vaaniq.voice.exceptions import ProviderNotFoundError

if TYPE_CHECKING:
    from vaaniq.voice.providers.base import STTProviderBase, TTSProviderBase


class ProviderRegistry:
    _stt: dict[str, type["STTProviderBase"]] = {}
    _tts: dict[str, type["TTSProviderBase"]] = {}

    # ── Registration (used as class decorators) ───────────────────────────────

    @classmethod
    def register_stt(cls, provider_class: type["STTProviderBase"]) -> type["STTProviderBase"]:
        """Register an STT provider. Used as a class decorator."""
        cls._stt[provider_class.provider_id] = provider_class
        return provider_class

    @classmethod
    def register_tts(cls, provider_class: type["TTSProviderBase"]) -> type["TTSProviderBase"]:
        """Register a TTS provider. Used as a class decorator."""
        cls._tts[provider_class.provider_id] = provider_class
        return provider_class

    # ── Lookup ────────────────────────────────────────────────────────────────

    @classmethod
    def get_stt(cls, provider_id: str) -> type["STTProviderBase"]:
        if provider_id not in cls._stt:
            raise ProviderNotFoundError("stt", provider_id)
        return cls._stt[provider_id]

    @classmethod
    def get_tts(cls, provider_id: str) -> type["TTSProviderBase"]:
        if provider_id not in cls._tts:
            raise ProviderNotFoundError("tts", provider_id)
        return cls._tts[provider_id]

    # ── Introspection ─────────────────────────────────────────────────────────

    @classmethod
    def all_stt(cls) -> dict[str, type["STTProviderBase"]]:
        return dict(cls._stt)

    @classmethod
    def all_tts(cls) -> dict[str, type["TTSProviderBase"]]:
        return dict(cls._tts)

    @classmethod
    def stt_provider_ids(cls) -> list[str]:
        return list(cls._stt.keys())

    @classmethod
    def tts_provider_ids(cls) -> list[str]:
        return list(cls._tts.keys())
