import os
import time
import logging
from typing import Optional
from config import settings
from ai.base import BaseAIProvider, AIResult

logger = logging.getLogger("echoquery.ai.mock")

class MockAIProvider(BaseAIProvider):
    """
    Deterministic AI provider strictly for development and testing environments.
    Guarantees no external API costs or external dependencies during local development.
    Hard-blocked from executing in production environments.
    """
    def __init__(self, model_name: str = "mock-whisper-v3"):
        self._model = model_name

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return self._model

    def is_healthy(self) -> bool:
        if settings.ENVIRONMENT == "production":
            return False
        return True

    def transcribe_and_analyze(self, audio_path: str, mime_type: str = "audio/wav") -> AIResult:
        if settings.ENVIRONMENT == "production":
            raise RuntimeError("MockAIProvider is strictly prohibited in production environments.")

        start_time = time.time()
        filename = os.path.basename(audio_path) if audio_path else "audio_track.wav"
        clean_name = filename.split(".")[0].replace("_", " ").replace("-", " ").title()

        # Deterministic transcript generation
        transcript = (
            f"Hello and welcome! This is the automated speech-to-text transcript for '{clean_name}'. "
            "The speaker explains the core architectural principles of distributed task engines, "
            "highlighting decoupled ingestion, asynchronous worker pools, transactional outbox durability, "
            "and fault-tolerant execution under high system load."
        )

        summary = (
            f"Automated Executive Briefing ({clean_name}): Discussion of high-availability distributed systems, "
            "message queue decoupling, transactional outbox pattern, and hybrid AI model inference."
        )

        sentiment = "POSITIVE (96.5% confidence)"
        skills = ["Distributed Systems", "FastAPI", "Transactional Outbox", "Celery", "Redis"]

        segments = [
            {"start_sec": 0.0, "end_sec": 4.5, "text": f"Hello and welcome! This is the transcript for {clean_name}."},
            {"start_sec": 4.5, "end_sec": 9.8, "text": "The speaker explains the core architectural principles of distributed task engines."},
            {"start_sec": 9.8, "end_sec": 15.2, "text": "Highlighting decoupled ingestion, asynchronous worker pools, and transactional outbox durability."}
        ]

        latency_ms = (time.time() - start_time) * 1000 + 45.0  # Simulated low latency

        return AIResult(
            transcript=transcript,
            summary=summary,
            sentiment=sentiment,
            provider=self.provider_name,
            model_name=self.model_name,
            latency_ms=round(latency_ms, 2),
            input_tokens=142,
            output_tokens=68,
            cost_cents=0.0,
            segments=segments,
            skills=skills
        )
