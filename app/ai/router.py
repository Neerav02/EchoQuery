import os
import logging
from typing import Optional, Dict
from config import settings
from ai.base import BaseAIProvider, AIResult
from ai.mock_provider import MockAIProvider
from ai.cloud_openai import CloudOpenAIProvider
from ai.cloud_gemini import CloudGeminiProvider

logger = logging.getLogger("echoquery.ai.router")

class HybridAIRouter:
    """
    Intelligent Hybrid AI Inference Router.
    Routes tasks between local AI models and cloud AI providers with automatic fallback,
    latency tracking, and usage telemetry.
    """
    def __init__(
        self,
        primary_provider: Optional[str] = None,
        fallback_provider: Optional[str] = None
    ):
        self.primary_name = (primary_provider or settings.AI_PRIMARY_PROVIDER or "mock").lower()
        self.fallback_name = (fallback_provider or settings.AI_FALLBACK_PROVIDER or "mock").lower()
        self._provider_cache: Dict[str, BaseAIProvider] = {}

    def get_provider(self, name: str) -> BaseAIProvider:
        name = name.lower()
        if name in self._provider_cache:
            return self._provider_cache[name]

        provider: BaseAIProvider
        if name == "mock":
            provider = MockAIProvider()
        elif name == "openai":
            provider = CloudOpenAIProvider()
        elif name == "gemini":
            provider = CloudGeminiProvider()
        elif name in ("local_whisper", "local", "whisper"):
            try:
                from ai.local_whisper import LocalWhisperProvider
                provider = LocalWhisperProvider()
            except ImportError:
                logger.warning("LocalWhisperProvider not yet loaded. Falling back to Mock.")
                provider = MockAIProvider()
        else:
            logger.warning(f"Unknown provider '{name}'. Defaulting to Mock.")
            provider = MockAIProvider()

        self._provider_cache[name] = provider
        return provider

    def transcribe_and_analyze(
        self,
        audio_path: str,
        mime_type: str = "audio/wav",
        preferred_provider: Optional[str] = None
    ) -> AIResult:
        """
        Executes AI transcription and analysis with resilient fallback.
        Tries primary provider first; if it fails or is unhealthy, routes to fallback provider.
        """
        target_name = (preferred_provider or self.primary_name).lower()
        primary_provider = self.get_provider(target_name)

        # Attempt Primary Provider
        if primary_provider.is_healthy():
            try:
                logger.info(f"Dispatching inference task to primary provider: {target_name}")
                result = primary_provider.transcribe_and_analyze(audio_path, mime_type)
                result.fallback_used = False
                return result
            except Exception as e:
                logger.warning(f"Primary AI provider '{target_name}' failed: {e}. Attempting fallback...")
        else:
            logger.info(f"Primary AI provider '{target_name}' is not healthy/configured. Attempting fallback...")

        # Attempt Fallback Provider
        if target_name == self.fallback_name:
            fallback_target = "mock" if settings.ENVIRONMENT != "production" else "gemini"
        else:
            fallback_target = self.fallback_name

        fallback_provider = self.get_provider(fallback_target)
        if not fallback_provider.is_healthy():
            raise RuntimeError(
                f"Both primary AI provider '{target_name}' and fallback provider '{fallback_target}' are unavailable."
            )

        logger.info(f"Routing to fallback AI provider: {fallback_target}")
        result = fallback_provider.transcribe_and_analyze(audio_path, mime_type)
        result.fallback_used = True
        result.original_provider = target_name
        return result

default_router = HybridAIRouter()

