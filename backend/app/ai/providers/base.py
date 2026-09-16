from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.schemas.resume import TextBlock


class AIProviderError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ProviderResponse:
    raw_content: str
    provider_name: str
    model_name: str
    latency_ms: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    usage_available: bool = False
    prompt_version: str = "unknown"


class ResumeAIProvider(ABC):
    @abstractmethod
    async def structure_resume(
        self,
        raw_text: str,
        blocks: list[TextBlock],
    ) -> ProviderResponse:
        """Return a JSON string that must be validated by the service layer."""


class JobAIProvider(ABC):
    @abstractmethod
    async def structure_job(self, raw_text: str) -> ProviderResponse:
        """Return JSON that must be validated as a JobRequirementProfile."""


class CareerQAProvider(ABC):
    @abstractmethod
    async def answer_question(self, prompt: str) -> ProviderResponse:
        """Return JSON that must be validated by the Career Assistant service."""
