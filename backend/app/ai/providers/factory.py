from __future__ import annotations

from collections.abc import Callable
from typing import cast

from app.ai.providers.base import CareerQAProvider, JobAIProvider, ResumeAIProvider
from app.ai.providers.mock import MockAIProvider
from app.ai.providers.openai_compatible import OpenAICompatibleProvider
from app.core.config import Settings
from app.core.exceptions import AppError

ProviderBuilder = Callable[[Settings], ResumeAIProvider]


def _build_mock(_settings: Settings) -> ResumeAIProvider:
    return MockAIProvider()


def _build_openai_compatible(settings: Settings) -> ResumeAIProvider:
    if not settings.openai_api_key:
        raise AppError(
            "AI_PROVIDER_NOT_CONFIGURED",
            "OpenAI 兼容 Provider 尚未配置 API key",
            503,
        )
    return OpenAICompatibleProvider(
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key,
        model=settings.openai_chat_model,
        temperature=settings.openai_temperature,
        timeout_seconds=settings.openai_timeout_seconds,
        http_retries=settings.openai_http_retries,
    )


_PROVIDER_BUILDERS: dict[str, ProviderBuilder] = {
    "mock": _build_mock,
    "openai_compatible": _build_openai_compatible,
}


def create_resume_ai_provider(settings: Settings) -> ResumeAIProvider:
    try:
        builder = _PROVIDER_BUILDERS[settings.ai_provider]
    except KeyError as exc:
        raise AppError("AI_PROVIDER_UNSUPPORTED", "不支持的 AI Provider", 500) from exc
    return builder(settings)


def create_job_ai_provider(settings: Settings) -> JobAIProvider:
    """Create the opt-in real Job parser without changing demo matching behavior."""
    if settings.ai_provider != "openai_compatible" or not settings.openai_api_key:
        raise AppError(
            "AI_PROVIDER_NOT_CONFIGURED",
            "Real Job parser requires AI_PROVIDER=openai_compatible and an API key",
            503,
        )
    return cast(JobAIProvider, _build_openai_compatible(settings))


def create_career_qa_provider(settings: Settings) -> CareerQAProvider:
    """Create the opt-in direct OpenAI-compatible QA provider for validation."""
    if settings.ai_provider != "openai_compatible" or not settings.openai_api_key:
        raise AppError(
            "AI_PROVIDER_NOT_CONFIGURED",
            "Real Career Assistant QA requires AI_PROVIDER=openai_compatible and an API key",
            503,
        )
    return cast(CareerQAProvider, _build_openai_compatible(settings))
