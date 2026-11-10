import pytest
import os
import tempfile
from unittest.mock import MagicMock

from ai.local_whisper import (
    get_optimal_device,
    WhisperModelRegistry,
    LocalWhisperProvider
)
from ai.base import AIResult

@pytest.fixture(autouse=True)
def clean_registry():
    WhisperModelRegistry.clear_cache()
    yield
    WhisperModelRegistry.clear_cache()

@pytest.fixture
def dummy_audio_file():
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)

# ==========================================
# 1. Device Tuning Tests
# ==========================================

def test_whisper_device_selection():
    device, compute_type = get_optimal_device("cpu")
    assert device == "cpu"
    assert compute_type == "int8"

    device_gpu, compute_gpu = get_optimal_device("cuda")
    assert device_gpu == "cuda"
    assert compute_gpu == "float16"

# ==========================================
# 2. Process Singleton Registry Tests
# ==========================================

def test_whisper_model_registry_caching(mocker):
    mock_loaded = MagicMock()
    mock_load = mocker.patch("whisper.load_model", return_value=mock_loaded)

    # First fetch: loads model
    engine1, model1 = WhisperModelRegistry.get_model("base", "cpu", "int8")
    assert engine1 == "openai_whisper"
    assert model1 == mock_loaded
    assert mock_load.call_count == 1

    # Second fetch: retrieved from process cache, no reloading
    engine2, model2 = WhisperModelRegistry.get_model("base", "cpu", "int8")
    assert model2 == mock_loaded
    assert mock_load.call_count == 1  # Not reloaded!

# ==========================================
# 3. Local Whisper Provider Transcription Tests
# ==========================================

def test_local_whisper_transcription(dummy_audio_file, mocker):
    mock_whisper_model = MagicMock()
    mock_whisper_model.transcribe.return_value = {
        "text": "Local inference audio transcription successfully generated.",
        "segments": [
            {"start": 0.0, "end": 3.0, "text": "Local inference audio transcription"},
            {"start": 3.0, "end": 5.5, "text": "successfully generated."}
        ]
    }
    mocker.patch("whisper.load_model", return_value=mock_whisper_model)

    provider = LocalWhisperProvider(model_size="base", device="cpu")
    assert provider.provider_name == "local_whisper"
    assert "whisper-base-cpu" in provider.model_name

    result = provider.transcribe_and_analyze(dummy_audio_file)
    assert isinstance(result, AIResult)
    assert result.provider == "local_whisper"
    assert result.transcript == "Local inference audio transcription successfully generated."
    assert len(result.segments) == 2
    assert result.cost_cents == 0.0
    assert result.latency_ms > 0

def test_local_whisper_missing_file_raises():
    provider = LocalWhisperProvider()
    with pytest.raises(FileNotFoundError):
        provider.transcribe_and_analyze("/non/existent/path/to/missing_file.wav")

