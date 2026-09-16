import pytest
from httpx import AsyncClient

from app.core.config import Settings


@pytest.mark.asyncio
async def test_health_reports_effective_demo_mode(client: AsyncClient) -> None:
    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "status": "ok",
        "ai_mode": "demo",
        "ai_provider": "mock",
        "dify_provider_mode": "fake",
    }


def test_ai_mode_is_derived_from_provider_configuration() -> None:
    assert Settings(ai_provider="mock", dify_provider_mode="fake").ai_mode == "demo"
    assert Settings(ai_provider="openai_compatible", dify_provider_mode="fake").ai_mode == "mixed"
    assert Settings(ai_provider="mock", dify_provider_mode="dify").ai_mode == "mixed"
    assert Settings(ai_provider="openai_compatible", dify_provider_mode="dify").ai_mode == "real"
