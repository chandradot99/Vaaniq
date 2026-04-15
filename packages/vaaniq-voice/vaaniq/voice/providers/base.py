"""
Base classes and data types for STT and TTS provider implementations.

Each provider is a class that:
  - declares provider_id and display_name as class variables
  - implements create_plugin(context) to return a LiveKit STT/TTS plugin
  - implements static_models() / static_voices() as hardcoded fallbacks
  - optionally overrides fetch_models() / fetch_voices() for live API data

Providers that don't support a capability (e.g. Cartesia has no STT) simply
don't implement that provider type. Providers that don't support voice selection
(e.g. Deepgram STT) leave supports_voices() returning False — the UI hides
the voice picker for those providers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from vaaniq.voice.pipeline.context import VoiceCallContext


# ── Data types ─────────────────────────────────────────────────────────────────

@dataclass
class ModelInfo:
    """Describes a single STT or TTS model offered by a provider."""

    id: str
    display_name: str
    description: str | None = None
    languages: list[str] = field(default_factory=list)
    """BCP-47 language codes this model supports. ['*'] means all languages."""
    is_default: bool = False


@dataclass
class VoiceInfo:
    """Describes a single TTS voice offered by a provider."""

    id: str
    name: str
    preview_url: str | None = None
    gender: str | None = None
    """'male' | 'female' | 'neutral' | None if unknown"""
    language: str | None = None
    """Primary language BCP-47 code, e.g. 'en', 'hi-IN'"""
    category: str | None = None
    """e.g. 'premade', 'cloned', 'professional', 'generated'"""
    description: str | None = None


# ── STT provider base ─────────────────────────────────────────────────────────

class STTProviderBase(ABC):
    """
    Abstract base class for all STT providers.

    Subclasses must set provider_id and display_name as ClassVars and
    implement create_plugin() and default_model_id().

    Optionally override:
      - static_models()  → hardcoded model list shown when API is unavailable
      - fetch_models()   → live model list from provider API (falls back to static)
    """

    provider_id: ClassVar[str]
    display_name: ClassVar[str]

    @classmethod
    @abstractmethod
    def create_plugin(cls, context: "VoiceCallContext"):
        """Return a LiveKit STT plugin configured for the given call context."""
        ...

    @classmethod
    @abstractmethod
    def default_model_id(cls) -> str:
        """The model ID to use when none is specified or the requested model is invalid."""
        ...

    @classmethod
    def static_models(cls) -> list[ModelInfo]:
        """
        Hardcoded model list — always available, no API call needed.
        Used as the fallback when fetch_models() fails or is not overridden.
        """
        return []

    @classmethod
    async def fetch_models(cls, api_key: str) -> list[ModelInfo]:
        """
        Fetch the live model list from the provider API.

        Default: returns static_models(). Override to add real API calls.
        Must never raise — catch exceptions and fall back to static_models().
        """
        return cls.static_models()


# ── TTS provider base ─────────────────────────────────────────────────────────

class TTSProviderBase(ABC):
    """
    Abstract base class for all TTS providers.

    Subclasses must set provider_id and display_name as ClassVars and
    implement create_plugin() and default_model_id().

    Optionally override:
      - static_models() / fetch_models()  → model listing
      - supports_voices()                 → whether voice selection is supported
      - static_voices() / fetch_voices()  → voice listing (only if supports_voices())
    """

    provider_id: ClassVar[str]
    display_name: ClassVar[str]

    @classmethod
    @abstractmethod
    def create_plugin(cls, context: "VoiceCallContext"):
        """Return a LiveKit TTS plugin configured for the given call context."""
        ...

    @classmethod
    @abstractmethod
    def default_model_id(cls) -> str:
        """The model ID to use when none is specified or the requested model is invalid."""
        ...

    @classmethod
    def static_models(cls) -> list[ModelInfo]:
        """Hardcoded model list — fallback when fetch_models() fails."""
        return []

    @classmethod
    async def fetch_models(cls, api_key: str) -> list[ModelInfo]:
        """
        Fetch the live model list from the provider API.
        Must never raise — catch exceptions and fall back to static_models().
        """
        return cls.static_models()

    @classmethod
    def supports_voices(cls) -> bool:
        """
        Whether this provider supports voice selection.
        When False, the UI hides the voice picker and voice_id is ignored.
        """
        return False

    @classmethod
    def static_voices(cls) -> list[VoiceInfo]:
        """
        Hardcoded voice list — fallback when fetch_voices() fails or provider
        has no API endpoint for voices (e.g. OpenAI).
        Returns [] when supports_voices() is False.
        """
        return []

    @classmethod
    async def fetch_voices(cls, api_key: str) -> list[VoiceInfo]:
        """
        Fetch the live voice list from the provider API.
        Must never raise — catch exceptions and fall back to static_voices().
        Returns [] when supports_voices() is False.
        """
        return cls.static_voices()
