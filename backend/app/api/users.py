from fastapi import APIRouter

from app.api.dependencies import CurrentUser, DbSession
from app.schemas.common import ApiResponse
from app.schemas.user import UserRead, UserUpdate
from app.services.users import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=ApiResponse[UserRead])
def get_me(current_user: CurrentUser) -> ApiResponse[UserRead]:
    return ApiResponse(data=UserRead.model_validate(current_user))


@router.patch("/me", response_model=ApiResponse[UserRead])
def update_me(
    payload: UserUpdate,
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[UserRead]:
    user = UserService(session).update_current_user(current_user, payload)
    return ApiResponse(data=user, message="资料已更新")
