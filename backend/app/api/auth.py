from fastapi import APIRouter, Request, status

from app.api.dependencies import AppSettings, DbSession
from app.core.exceptions import AppError
from app.core.rate_limit import login_rate_limit_key, login_rate_limiter
from app.schemas.auth import (
    AuthSession,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
)
from app.schemas.common import ApiResponse
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=ApiResponse[AuthSession],
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: RegisterRequest,
    session: DbSession,
    settings: AppSettings,
) -> ApiResponse[AuthSession]:
    auth_session = AuthService(session, settings).register(
        payload.email,
        payload.password,
        payload.display_name,
    )
    return ApiResponse(data=auth_session, message="注册成功")


@router.post("/login", response_model=ApiResponse[AuthSession])
def login(
    request: Request,
    payload: LoginRequest,
    session: DbSession,
    settings: AppSettings,
) -> ApiResponse[AuthSession]:
    rate_limit_key = login_rate_limit_key(request, payload.email)
    login_rate_limiter.check(rate_limit_key, settings)
    try:
        auth_session = AuthService(session, settings).login(payload.email, payload.password)
    except AppError as exc:
        if exc.code == "INVALID_CREDENTIALS":
            login_rate_limiter.record_failure(rate_limit_key, settings)
        raise
    login_rate_limiter.clear(rate_limit_key)
    return ApiResponse(data=auth_session, message="登录成功")


@router.post("/refresh", response_model=ApiResponse[TokenPair])
def refresh(
    payload: RefreshRequest,
    session: DbSession,
    settings: AppSettings,
) -> ApiResponse[TokenPair]:
    token_pair = AuthService(session, settings).refresh(payload.refresh_token)
    return ApiResponse(data=token_pair, message="令牌已刷新")


@router.post("/logout", response_model=ApiResponse[dict[str, bool]])
def logout(
    payload: LogoutRequest,
    session: DbSession,
    settings: AppSettings,
) -> ApiResponse[dict[str, bool]]:
    AuthService(session, settings).logout(payload.refresh_token)
    return ApiResponse(data={"logged_out": True}, message="已退出登录")
