"""
Unit tests for the STT provider factory.
No network calls — just verifies factory routing and error handling.
"""

import pytest
from unittest.mock import patch, MagicMock

from vaaniq.voice.exceptions import MissingAPIKeyError, ProviderNotFoundError
from vaaniq.voice.services.stt.base import create_stt_service


def _org_keys(provider: str, key: str = "test-key") -> dict:
    return {provider: key}


# ── Provider routing ──────────────────────────────────────────────────────────

def test_deepgram_returns_service():
    with patch("vaaniq.voice.services.stt.deepgram.DeepgramSTTService") as MockSvc:
        MockSvc.return_value = MagicMock()
        svc = create_stt_service("deepgram", _org_keys("deepgram"))
        assert svc is MockSvc.return_value
        MockSvc.assert_called_once()


def test_assemblyai_returns_service():
    with patch("vaaniq.voice.services.stt.assemblyai.AssemblyAISTTService") as MockSvc:
        MockSvc.return_value = MagicMock()
        svc = create_stt_service("assemblyai", _org_keys("assemblyai"))
        assert svc is MockSvc.return_value
        MockSvc.assert_called_once()


def test_unknown_provider_raises():
    with pytest.raises(ProviderNotFoundError) as exc:
        create_stt_service("google", _org_keys("google"))
    assert exc.value.provider == "google"
    assert exc.value.category == "STT"


# ── API key handling ──────────────────────────────────────────────────────────

def test_missing_key_raises():
    with pytest.raises(MissingAPIKeyError) as exc:
        create_stt_service("deepgram", {})  # no deepgram key
    assert exc.value.provider == "deepgram"


def test_dict_key_extracted():
    """org_keys may store keys as dicts: {"api_key": "..."}"""
    with patch("vaaniq.voice.services.stt.deepgram.DeepgramSTTService") as MockSvc:
        MockSvc.return_value = MagicMock()
        create_stt_service("deepgram", {"deepgram": {"api_key": "dg-real-key"}})
        call_kwargs = MockSvc.call_args.kwargs
        assert call_kwargs["api_key"] == "dg-real-key"


def test_empty_dict_key_raises():
    with pytest.raises(MissingAPIKeyError):
        create_stt_service("deepgram", {"deepgram": {"api_key": ""}})


# ── Deepgram config ───────────────────────────────────────────────────────────

def test_deepgram_uses_nova3_by_default():
    with patch("vaaniq.voice.services.stt.deepgram.DeepgramSTTService") as MockSvc:
        MockSvc.return_value = MagicMock()
        create_stt_service("deepgram", _org_keys("deepgram"), language="en-IN")
        live_options = MockSvc.call_args.kwargs["live_options"]
        assert live_options.model == "nova-3"
        assert live_options.language == "en-IN"


def test_deepgram_sample_rate_passed():
    with patch("vaaniq.voice.services.stt.deepgram.DeepgramSTTService") as MockSvc:
        MockSvc.return_value = MagicMock()
        create_stt_service("deepgram", _org_keys("deepgram"), sample_rate=8000)
        assert MockSvc.call_args.kwargs["sample_rate"] == 8000
