from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.schemas.common import ApiResponse

router = APIRouter(tags=["health"])


class HealthData(BaseModel):
    status: Literal["ok"] = "ok"
    ai_mode: Literal["demo", "mixed", "real"]
    ai_provider: Literal["mock", "openai_compatible"]
    dify_provider_mode: Literal["fake", "dify"]


@router.get("/health", response_model=ApiResponse[HealthData])
def health_check(settings: Annotated[Settings, Depends(get_settings)]) -> ApiResponse[HealthData]:
    return ApiResponse(
        data=HealthData(
            ai_mode=settings.ai_mode,
            ai_provider=settings.ai_provider,
            dify_provider_mode=settings.dify_provider_mode,
        )
    )
