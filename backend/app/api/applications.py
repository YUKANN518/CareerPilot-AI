from fastapi import APIRouter, Query, status

from app.api.dependencies import CurrentUser, DbSession
from app.models.enums import ApplicationStatus
from app.schemas.applications import (
    ApplicationBoardRead,
    ApplicationCreate,
    ApplicationRead,
    ApplicationStatusUpdate,
    ApplicationUpdate,
)
from app.schemas.common import ApiResponse
from app.services.applications import ApplicationService

router = APIRouter(prefix="/applications", tags=["applications"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ApiResponse[ApplicationRead])
def create_application(
    payload: ApplicationCreate,
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[ApplicationRead]:
    return ApiResponse(
        data=ApplicationService(session).create(current_user, payload),
        message="投递记录已创建",
    )


@router.get("", response_model=ApiResponse[list[ApplicationRead]])
def list_applications(
    current_user: CurrentUser,
    session: DbSession,
    status_filter: ApplicationStatus | None = Query(default=None, alias="status"),  # noqa: B008
) -> ApiResponse[list[ApplicationRead]]:
    return ApiResponse(data=ApplicationService(session).list(current_user, status_filter))


@router.get("/board", response_model=ApiResponse[ApplicationBoardRead])
def get_application_board(
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[ApplicationBoardRead]:
    return ApiResponse(data=ApplicationService(session).board(current_user))


@router.get("/{application_id}", response_model=ApiResponse[ApplicationRead])
def get_application(
    application_id: int,
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[ApplicationRead]:
    return ApiResponse(data=ApplicationService(session).get(current_user, application_id))


@router.patch("/{application_id}", response_model=ApiResponse[ApplicationRead])
def update_application(
    application_id: int,
    payload: ApplicationUpdate,
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[ApplicationRead]:
    return ApiResponse(
        data=ApplicationService(session).update(current_user, application_id, payload),
        message="投递记录已更新",
    )


@router.post("/{application_id}/status", response_model=ApiResponse[ApplicationRead])
def update_application_status(
    application_id: int,
    payload: ApplicationStatusUpdate,
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[ApplicationRead]:
    return ApiResponse(
        data=ApplicationService(session).change_status(current_user, application_id, payload),
        message="投递状态已更新",
    )


@router.delete("/{application_id}", response_model=ApiResponse[dict[str, bool]])
def delete_application(
    application_id: int,
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[dict[str, bool]]:
    ApplicationService(session).delete(current_user, application_id)
    return ApiResponse(data={"deleted": True}, message="投递记录已删除")
