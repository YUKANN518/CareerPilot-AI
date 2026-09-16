from fastapi import APIRouter

from app.api.dependencies import CurrentUser, DbSession
from app.schemas.common import ApiResponse
from app.schemas.dashboard import DashboardRead
from app.services.dashboard import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get(
    "",
    response_model=ApiResponse[DashboardRead],
    summary="Get the authenticated user's real dashboard aggregation",
)
def get_dashboard(
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse[DashboardRead]:
    return ApiResponse(
        data=DashboardService(session).get(current_user),
        message="Dashboard loaded",
    )
