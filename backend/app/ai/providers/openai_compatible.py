from __future__ import annotations

import asyncio
import json
from time import perf_counter
from typing import Any

import httpx

from app.ai.prompts import (
    CAREER_RAG_PROMPT_VERSION,
    JOB_PARSER_PROMPT_VERSION,
    RESUME_PARSER_PROMPT_VERSION,
)
from app.ai.providers.base import (
    AIProviderError,
    CareerQAProvider,
    JobAIProvider,
    ProviderResponse,
    ResumeAIProvider,
)
from app.schemas.ai_provider import JobRequirementProfile
from app.schemas.career_assistant import KnowledgeQAWorkflowOutput
from app.schemas.resume import ResumeProfile, TextBlock

RETRYABLE_HTTP_STATUS = frozenset({408, 429, 500, 502, 503, 504})


class OpenAICompatibleProvider(ResumeAIProvider, JobAIProvider, CareerQAProvider):
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float,
        timeout_seconds: float,
        http_retries: int,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.timeout = httpx.Timeout(
            connect=min(timeout_seconds, 10),
            read=timeout_seconds,
            write=timeout_seconds,
            pool=min(timeout_seconds, 10),
        )
        # Retry only in the explicit status/transport policy below.  The httpx
        # transport retry knob cannot distinguish invalid credentials from a
        # transient 5xx and would make observability misleading.
        self.http_retries = max(0, min(http_retries, 3))

    async def structure_resume(
        self,
        raw_text: str,
        blocks: list[TextBlock],
    ) -> ProviderResponse:
        prompt = self._build_prompt(raw_text, blocks)
        return await self.complete_json(
            system_prompt=(
                "You extract resume facts. Return only JSON matching the provided schema. "
                "Never invent facts or database ids. Evidence must quote the supplied text."
            ),
            user_prompt=prompt,
            schema=ResumeProfile.model_json_schema(),
            prompt_version=RESUME_PARSER_PROMPT_VERSION,
        )

    async def structure_job(self, raw_text: str) -> ProviderResponse:
        prompt = (
            "JSON schema:\n"
            f"{json.dumps(JobRequirementProfile.model_json_schema(), ensure_ascii=False)}\n\n"
            "Extract only requirements explicitly supported by the supplied job description. "
            "Do not turn related concepts into exact tools. Every skill evidence_text must quote "
            f"the source text.\n\nJob description:\n{raw_text[:30_000]}"
        )
        return await self.complete_json(
            system_prompt=(
                "You extract job requirements. Return only JSON matching the provided schema. "
                "Do not invent employer, eligibility, education or skills."
            ),
            user_prompt=prompt,
            schema=JobRequirementProfile.model_json_schema(),
            prompt_version=JOB_PARSER_PROMPT_VERSION,
        )

    async def answer_question(self, prompt: str) -> ProviderResponse:
        schema = json.dumps(KnowledgeQAWorkflowOutput.model_json_schema(), ensure_ascii=False)
        return await self.complete_json(
            system_prompt=(
                "You answer a grounded career question. Return only JSON matching the provided "
                "schema. Use only the supplied evidence, cite its stable keys, and set "
                "insufficient_evidence when the evidence does not support an answer."
            ),
            user_prompt=f"JSON schema:\n{schema}\n\n{prompt}",
            schema=KnowledgeQAWorkflowOutput.model_json_schema(),
            prompt_version=CAREER_RAG_PROMPT_VERSION,
        )

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        prompt_version: str,
    ) -> ProviderResponse:
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        started = perf_counter()
        body = await self._request(payload)
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIProviderError(
                "AI_PROVIDER_RESPONSE_INVALID",
                "AI provider returned an invalid chat completion shape",
            ) from exc
        if not isinstance(content, str) or not content.strip():
            raise AIProviderError(
                "AI_PROVIDER_RESPONSE_INVALID",
                "AI provider returned empty structured content",
            )
        usage = body.get("usage")
        usage_dict = usage if isinstance(usage, dict) else {}
        prompt_tokens = _usage_int(usage_dict.get("prompt_tokens"))
        completion_tokens = _usage_int(usage_dict.get("completion_tokens"))
        total_tokens = _usage_int(usage_dict.get("total_tokens"))
        available = any(
            value is not None for value in (prompt_tokens, completion_tokens, total_tokens)
        )
        return ProviderResponse(
            raw_content=content,
            provider_name="openai_compatible",
            model_name=self.model,
            latency_ms=max(1, int((perf_counter() - started) * 1000)),
            prompt_tokens=prompt_tokens or 0,
            completion_tokens=completion_tokens or 0,
            total_tokens=total_tokens or ((prompt_tokens or 0) + (completion_tokens or 0)),
            usage_available=available,
            prompt_version=prompt_version,
        )

    async def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        last_code = "AI_PROVIDER_REQUEST_FAILED"
        for attempt in range(self.http_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json=payload,
                    )
            except httpx.TimeoutException as exc:
                last_code = "AI_PROVIDER_TIMEOUT"
                if attempt >= self.http_retries:
                    raise AIProviderError(last_code, "AI provider request timed out") from exc
                await asyncio.sleep(0.25 * (2**attempt))
                continue
            except httpx.HTTPError as exc:
                last_code = "AI_PROVIDER_UNAVAILABLE"
                if attempt >= self.http_retries:
                    raise AIProviderError(last_code, "AI provider is unavailable") from exc
                await asyncio.sleep(0.25 * (2**attempt))
                continue

            if response.status_code in {401, 403}:
                raise AIProviderError(
                    "AI_PROVIDER_AUTH_FAILED",
                    "AI provider authentication failed",
                )
            if response.status_code >= 400 and response.status_code not in RETRYABLE_HTTP_STATUS:
                raise AIProviderError(
                    "AI_PROVIDER_REQUEST_REJECTED",
                    f"AI provider rejected the request (HTTP {response.status_code})",
                )
            if response.status_code in RETRYABLE_HTTP_STATUS:
                last_code = (
                    "AI_PROVIDER_RATE_LIMITED"
                    if response.status_code == 429
                    else "AI_PROVIDER_RETRYABLE"
                )
                if attempt >= self.http_retries:
                    raise AIProviderError(
                        last_code,
                        f"AI provider returned retryable HTTP status {response.status_code}",
                    )
                await asyncio.sleep(0.25 * (2**attempt))
                continue
            try:
                body = response.json()
            except (ValueError, json.JSONDecodeError) as exc:
                raise AIProviderError(
                    "AI_PROVIDER_RESPONSE_INVALID",
                    "AI provider returned a non-JSON response",
                ) from exc
            if not isinstance(body, dict):
                raise AIProviderError(
                    "AI_PROVIDER_RESPONSE_INVALID",
                    "AI provider response was not an object",
                )
            return body
        raise AIProviderError(last_code, "AI provider request failed")

    @staticmethod
    def _build_prompt(raw_text: str, blocks: list[TextBlock]) -> str:
        source_blocks = "\n".join(
            f"[{index}] {block.model_dump_json()}" for index, block in enumerate(blocks)
        )
        schema = json.dumps(ResumeProfile.model_json_schema(), ensure_ascii=False)
        return (
            f"JSON schema:\n{schema}\n\n"
            f"Source blocks:\n{source_blocks[:20_000]}\n\n"
            f"Resume text:\n{raw_text[:30_000]}"
        )


def _usage_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
