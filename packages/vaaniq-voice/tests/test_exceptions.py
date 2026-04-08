from vaaniq.voice.exceptions import MissingAPIKeyError, ProviderNotFoundError


def test_provider_not_found_error():
    err = ProviderNotFoundError("STT", "google")
    assert "google" in str(err)
    assert err.provider == "google"
    assert err.category == "STT"


def test_missing_api_key_error():
    err = MissingAPIKeyError("deepgram")
    assert "deepgram" in str(err)
    assert err.provider == "deepgram"
