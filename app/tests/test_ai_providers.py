import pytest
import os
import tempfile
from unittest.mock import MagicMock, patch
import httpx

from config import settings
from ai.base import AIResult
from ai.mock_provider import MockAIProvider
from ai.cloud_openai import CloudOpenAIProvider
from ai.cloud_gemini import CloudGeminiProvider
from ai.router import HybridAIRouter

@pytest.fixture
def dummy_audio_file():
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)

# ==========================================
# 1. Mock Provider Tests
# ==========================================

def test_mock_provider_success(dummy_audio_file):
    provider = MockAIProvider()
    assert provider.is_healthy() is True
    assert provider.provider_name == "mock"

    result = provider.transcribe_and_analyze(dummy_audio_file)
    assert isinstance(result, AIResult)
    assert "transcript" in result.transcript.lower() or "automated" in result.transcript.lower()
    assert result.summary is not None
    assert result.sentiment.startswith("POSITIVE")
    assert len(result.segments) > 0
    assert result.cost_cents == 0.0

def test_mock_provider_blocked_in_production(dummy_audio_file, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    provider = MockAIProvider()
    assert provider.is_healthy() is False

    with pytest.raises(RuntimeError, match="strictly prohibited in production"):
        provider.transcribe_and_analyze(dummy_audio_file)

# ==========================================
# 2. OpenAI Cloud Provider Tests
# ==========================================

def test_openai_health_check():
    unconfigured = CloudOpenAIProvider(api_key=None)
    assert unconfigured.is_healthy() is False

    configured = CloudOpenAIProvider(api_key="sk-test-openai-valid-api-key-here-12345")
    assert configured.is_healthy() is True

def test_openai_mocked_transcription(dummy_audio_file, mocker):
    provider = CloudOpenAIProvider(api_key="sk-test-valid-key-abcdef123456789")

    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "text": "Welcome to EchoQuery distributed task engine.",
        "segments": [
            {"start": 0.0, "end": 2.5, "text": "Welcome to EchoQuery"},
            {"start": 2.5, "end": 5.0, "text": "distributed task engine."}
        ]
    }

    mocker.patch("httpx.Client.post", return_value=mock_resp)

    result = provider.transcribe_and_analyze(dummy_audio_file)
    assert result.provider == "openai"
    assert result.transcript == "Welcome to EchoQuery distributed task engine."
    assert len(result.segments) == 2
    assert result.latency_ms > 0

def test_openai_rate_limit_retry(dummy_audio_file, mocker):
    provider = CloudOpenAIProvider(api_key="sk-test-valid-key-abcdef123456789")

    # Simulate 429 rate limit on first call, then 200 on second call
    err_resp = mocker.MagicMock()
    err_resp.status_code = 429
    err_call = httpx.HTTPStatusError("Rate Limit", request=mocker.MagicMock(), response=err_resp)

    success_resp = mocker.MagicMock()
    success_resp.status_code = 200
    success_resp.json.return_value = {"text": "Retried successfully after rate limit", "segments": []}

    mock_post = mocker.patch("httpx.Client.post", side_effect=[err_call, success_resp])
    mocker.patch("time.sleep") # Don't wait in tests

    result = provider.transcribe_and_analyze(dummy_audio_file)
    assert result.transcript == "Retried successfully after rate limit"
    assert mock_post.call_count == 2

# ==========================================
# 3. Google Gemini Multimodal Provider Tests
# ==========================================

def test_gemini_health_check():
    unconfigured = CloudGeminiProvider(api_key=None)
    assert unconfigured.is_healthy() is False

    configured = CloudGeminiProvider(api_key="AIzaSyDummyGeminiKeyValid12345")
    assert configured.is_healthy() is True

def test_gemini_mocked_transcription(dummy_audio_file, mocker):
    provider = CloudGeminiProvider(api_key="AIzaSyDummyGeminiKeyValid12345")

    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": '{"transcript": "Gemini verbatim transcript audio.", "summary": "Executive briefing from Gemini.", "sentiment": "POSITIVE (98.0%)", "skills": ["Gemini", "AI"]}'
                        }
                    ]
                }
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 250,
            "candidatesTokenCount": 80
        }
    }

    mocker.patch("httpx.Client.post", return_value=mock_resp)

    result = provider.transcribe_and_analyze(dummy_audio_file)
    assert result.provider == "gemini"
    assert result.transcript == "Gemini verbatim transcript audio."
    assert result.summary == "Executive briefing from Gemini."
    assert result.sentiment == "POSITIVE (98.0%)"
    assert result.input_tokens == 250
    assert result.output_tokens == 80

# ==========================================
# 4. Hybrid AI Router & Fallback Tests
# ==========================================

def test_router_primary_routing(dummy_audio_file):
    router = HybridAIRouter(primary_provider="mock", fallback_provider="mock")
    result = router.transcribe_and_analyze(dummy_audio_file)

    assert result.provider == "mock"
    assert result.fallback_used is False
    assert result.original_provider is None

def test_router_automatic_fallback(dummy_audio_file, mocker):
    # Primary is unconfigured OpenAI (missing key), Fallback is Mock
    router = HybridAIRouter(primary_provider="openai", fallback_provider="mock")
    
    result = router.transcribe_and_analyze(dummy_audio_file)
    assert result.provider == "mock"
    assert result.fallback_used is True
    assert result.original_provider == "openai"

def test_router_unhealthy_fallback_raises_error(dummy_audio_file):
    # Both providers unconfigured/unhealthy
    router = HybridAIRouter(primary_provider="openai", fallback_provider="gemini")
    
    with pytest.raises(RuntimeError, match="Both primary AI provider .* and fallback provider .* are unavailable"):
        router.transcribe_and_analyze(dummy_audio_file)

