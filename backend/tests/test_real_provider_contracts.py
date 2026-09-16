import pytest
from pydantic import ValidationError

from app.ai.providers.base import AIProviderError, ProviderResponse
from app.ai.providers.factory import create_job_ai_provider
from app.ai.providers.openai_compatible import OpenAICompatibleProvider
from app.core.config import Settings
from app.core.exceptions import AppError
from app.schemas.ai_provider import JobRequirementProfile, JobSkillExtraction


def test_job_requirement_schema_requires_evidence_and_rejects_extra_fields() -> None:
    skill = JobSkillExtraction(
        name="Python",
        required=True,
        evidence_text="Python services",
    )
    profile = JobRequirementProfile(
        title="Backend Engineer",
        required_skills=[skill],
        summary="Python backend role",
    )
    assert profile.required_skills[0].evidence_text == "Python services"

    with pytest.raises(ValidationError):
        JobSkillExtraction(
            name="Python",
            required=True,
            evidence_text="",
        )
    with pytest.raises(ValidationError):
        JobRequirementProfile.model_validate(
            {**profile.model_dump(), "unexpected": "must fail"}
        )


def test_real_job_provider_never_silently_falls_back_to_mock() -> None:
    settings = Settings(ai_provider="mock", openai_api_key="")
    with pytest.raises(AppError) as exc_info:
        create_job_ai_provider(settings)
    assert exc_info.value.code == "AI_PROVIDER_NOT_CONFIGURED"


def test_provider_response_marks_usage_unknown_when_provider_omits_usage() -> None:
    response = ProviderResponse(
        raw_content="{}",
        provider_name="openai_compatible",
        model_name="deepseek-v4-flash",
        latency_ms=12,
    )
    assert response.usage_available is False
    assert response.prompt_version == "unknown"


@pytest.mark.asyncio
async def test_openai_provider_retries_transient_status_then_returns_structured_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def __init__(self, status_code: int, body: dict[str, object]) -> None:
            self.status_code = status_code
            self._body = body

        def json(self) -> dict[str, object]:
            return self._body

    responses = [
        FakeResponse(503, {}),
        FakeResponse(
            200,
            {
                "choices": [{"message": {"content": '{"title":"Backend"}'}}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7},
            },
        ),
    ]
    calls = 0

    class FakeClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def post(self, *_args: object, **_kwargs: object) -> FakeResponse:
            nonlocal calls
            calls += 1
            return responses.pop(0)

    monkeypatch.setattr("app.ai.providers.openai_compatible.httpx.AsyncClient", FakeClient)
    provider = OpenAICompatibleProvider(
        base_url="https://example.invalid",
        api_key="test-key",
        model="test-model",
        temperature=0.0,
        timeout_seconds=1.0,
        http_retries=1,
    )
    response = await provider.complete_json(
        system_prompt="system",
        user_prompt="user",
        schema={},
        prompt_version="test-v1",
    )
    assert calls == 2
    assert response.usage_available is True
    assert response.total_tokens == 7
    assert response.prompt_version == "test-v1"


@pytest.mark.asyncio
async def test_openai_provider_does_not_retry_invalid_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        status_code = 401

        def json(self) -> dict[str, object]:
            return {}

    calls = 0

    class FakeClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def post(self, *_args: object, **_kwargs: object) -> FakeResponse:
            nonlocal calls
            calls += 1
            return FakeResponse()

    monkeypatch.setattr("app.ai.providers.openai_compatible.httpx.AsyncClient", FakeClient)
    provider = OpenAICompatibleProvider(
        base_url="https://example.invalid",
        api_key="bad-key",
        model="test-model",
        temperature=0.0,
        timeout_seconds=1.0,
        http_retries=3,
    )
    with pytest.raises(AIProviderError) as exc_info:
        await provider.complete_json(
            system_prompt="system",
            user_prompt="user",
            schema={},
            prompt_version="test-v1",
        )
    assert exc_info.value.code == "AI_PROVIDER_AUTH_FAILED"
    assert calls == 1
