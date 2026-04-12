class VoiceError(Exception):
    """Base exception for vaaniq-voice."""


class VoiceConfigError(VoiceError):
    """Raised when voice pipeline configuration is invalid (missing provider, bad keys, etc.)."""


class AgentError(VoiceError):
    """Raised when the LiveKit agent fails to start or crashes mid-call."""


class ProviderNotFoundError(VoiceConfigError):
    """Raised when the requested STT, TTS, or telephony provider is not registered."""

    def __init__(self, category: str, provider: str) -> None:
        super().__init__(f"{category} provider '{provider}' is not supported. Check your integration settings.")
        self.category = category
        self.provider = provider


class MissingAPIKeyError(VoiceConfigError):
    """Raised when a required BYOK API key is not found in org_keys."""

    def __init__(self, provider: str) -> None:
        super().__init__(f"No API key found for provider '{provider}'. Add it via Settings → Integrations.")
        self.provider = provider
