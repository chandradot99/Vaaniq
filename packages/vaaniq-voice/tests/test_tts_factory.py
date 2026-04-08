"""
Unit tests for the TTS provider factory.
No network calls — just verifies factory routing and error handling.
"""

from unittest.mock import MagicMock, patch

import pytest
from vaaniq.voice.exceptions import MissingAPIKeyError, ProviderNotFoundError
from vaaniq.voice.services.tts.base import create_tts_service


def _org_keys(provider: str, key: str = "test-key") -> dict:
    return {provider: key}


# ── Provider routing ──────────────────────────────────────────────────────────

def test_cartesia_returns_service():
    with patch("vaaniq.voice.services.tts.cartesia.CartesiaTTSService") as MockSvc:
        MockSvc.return_value = MagicMock()
        svc = create_tts_service("cartesia", _org_keys("cartesia"))
        assert svc is MockSvc.return_value


def test_elevenlabs_returns_service():
    with patch("vaaniq.voice.services.tts.elevenlabs.ElevenLabsTTSService") as MockSvc:
        MockSvc.return_value = MagicMock()
        svc = create_tts_service("elevenlabs", _org_keys("elevenlabs"))
        assert svc is MockSvc.return_value


def test_azure_returns_service():
    with patch("vaaniq.voice.services.tts.azure.AzureTTSService") as MockSvc:
        MockSvc.return_value = MagicMock()
        svc = create_tts_service("azure", {"azure": {"api_key": "az-key", "region": "eastus"}})
        assert svc is MockSvc.return_value


def test_unknown_provider_raises():
    with pytest.raises(ProviderNotFoundError) as exc:
        create_tts_service("google", _org_keys("google"))
    assert exc.value.provider == "google"
    assert exc.value.category == "TTS"


# ── API key handling ──────────────────────────────────────────────────────────

def test_missing_key_raises():
    with pytest.raises(MissingAPIKeyError) as exc:
        create_tts_service("cartesia", {})
    assert exc.value.provider == "cartesia"


def test_dict_key_extracted():
    with patch("vaaniq.voice.services.tts.cartesia.CartesiaTTSService") as MockSvc:
        MockSvc.return_value = MagicMock()
        create_tts_service("cartesia", {"cartesia": {"api_key": "cart-key"}})
        assert MockSvc.call_args.kwargs["api_key"] == "cart-key"


# ── Provider-specific config ──────────────────────────────────────────────────

def test_cartesia_uses_sonic3_by_default():
    with patch("vaaniq.voice.services.tts.cartesia.CartesiaTTSService") as MockSvc:
        MockSvc.return_value = MagicMock()
        create_tts_service("cartesia", _org_keys("cartesia"))
        assert MockSvc.call_args.kwargs["model"] == "sonic-3"


def test_cartesia_voice_id_passed():
    with patch("vaaniq.voice.services.tts.cartesia.CartesiaTTSService") as MockSvc:
        MockSvc.return_value = MagicMock()
        create_tts_service("cartesia", _org_keys("cartesia"), voice_id="my-voice-id")
        assert MockSvc.call_args.kwargs["voice_id"] == "my-voice-id"


def test_elevenlabs_uses_flash_by_default():
    with patch("vaaniq.voice.services.tts.elevenlabs.ElevenLabsTTSService") as MockSvc:
        MockSvc.return_value = MagicMock()
        create_tts_service("elevenlabs", _org_keys("elevenlabs"))
        assert MockSvc.call_args.kwargs["model"] == "eleven_flash_v2_5"


def test_azure_auto_selects_hindi_voice():
    with patch("vaaniq.voice.services.tts.azure.AzureTTSService") as MockSvc:
        MockSvc.return_value = MagicMock()
        create_tts_service(
            "azure",
            {"azure": {"api_key": "az-key", "region": "eastus"}},
            language="hi-IN",
        )
        assert MockSvc.call_args.kwargs["voice"] == "hi-IN-SwaraNeural"


def test_azure_auto_selects_tamil_voice():
    with patch("vaaniq.voice.services.tts.azure.AzureTTSService") as MockSvc:
        MockSvc.return_value = MagicMock()
        create_tts_service(
            "azure",
            {"azure": {"api_key": "az-key"}},
            language="ta-IN",
        )
        assert MockSvc.call_args.kwargs["voice"] == "ta-IN-PallaviNeural"


def test_azure_region_from_org_keys():
    with patch("vaaniq.voice.services.tts.azure.AzureTTSService") as MockSvc:
        MockSvc.return_value = MagicMock()
        create_tts_service(
            "azure",
            {"azure": {"api_key": "az-key", "region": "southeastasia"}},
        )
        assert MockSvc.call_args.kwargs["region"] == "southeastasia"


def test_sample_rate_passed_to_all_providers():
    for provider in ["cartesia", "elevenlabs"]:
        module = f"vaaniq.voice.services.tts.{provider}"
        cls = "CartesiaTTSService" if provider == "cartesia" else "ElevenLabsTTSService"
        with patch(f"{module}.{cls}") as MockSvc:
            MockSvc.return_value = MagicMock()
            create_tts_service(provider, _org_keys(provider), sample_rate=8000)
            assert MockSvc.call_args.kwargs["sample_rate"] == 8000
