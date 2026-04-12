from vaaniq.voice.exceptions import (
    AgentError,
    MissingAPIKeyError,
    ProviderNotFoundError,
    VoiceConfigError,
    VoiceError,
)


def test_provider_not_found_error():
    err = ProviderNotFoundError("stt", "google")
    assert "google" in str(err)
    assert err.provider == "google"
    assert err.category == "stt"


def test_missing_api_key_error():
    err = MissingAPIKeyError("deepgram")
    assert "deepgram" in str(err)
    assert err.provider == "deepgram"


def test_exception_hierarchy():
    assert issubclass(VoiceConfigError, VoiceError)
    assert issubclass(ProviderNotFoundError, VoiceConfigError)
    assert issubclass(MissingAPIKeyError, VoiceConfigError)
    assert issubclass(AgentError, VoiceError)
