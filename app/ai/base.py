from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class Segment:
    start_sec: float
    end_sec: float
    text: str

@dataclass
class AIResult:
    transcript: str
    summary: str
    sentiment: str
    provider: str
    model_name: str
    latency_ms: float
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cost_cents: Optional[float] = None
    segments: List[Dict[str, Any]] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)
    fallback_used: bool = False
    original_provider: Optional[str] = None

class BaseAIProvider(ABC):
    """Abstract interface defining required capabilities for any EchoQuery AI inference engine."""

    @abstractmethod
    def transcribe_and_analyze(self, audio_path: str, mime_type: str = "audio/wav") -> AIResult:
        """
        Executes speech-to-text transcription and downstream analytical intelligence (summarization, sentiment).
        Takes local file path to audio media and returns structured AIResult.
        """
        pass

    @abstractmethod
    def is_healthy(self) -> bool:
        """Validates API credentials, connectivity, or local model cache availability."""
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique provider identifier (e.g. 'openai', 'gemini', 'local_whisper', 'mock')."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Configured model name."""
        pass

