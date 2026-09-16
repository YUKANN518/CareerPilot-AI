from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.ai.providers.base import ResumeAIProvider
from app.ai.providers.factory import create_resume_ai_provider
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.core.security import decode_token
from app.db.session import get_db_session
from app.models.enums import UserRole
from app.models.users import User
from app.repositories.users import UserRepository

bearer_scheme = HTTPBearer(auto_error=False)
DbSession = Annotated[Session, Depends(get_db_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def get_resume_ai_provider(settings: AppSettings) -> ResumeAIProvider:
    return create_resume_ai_provider(settings)


ResumeProvider = Annotated[ResumeAIProvider, Depends(get_resume_ai_provider)]


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: DbSession,
    settings: AppSettings,
) -> User:
    if credentials is None:
        raise AppError("AUTH_REQUIRED", "请先登录", 401)
    payload = decode_token(credentials.credentials, "access", settings)
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AppError("INVALID_TOKEN", "令牌内容无效", 401) from exc

    user = UserRepository(session).get_by_id(user_id)
    if user is None:
        raise AppError("USER_NOT_FOUND", "用户不存在", 401)
    if not user.is_active:
        raise AppError("USER_DISABLED", "账号已停用", 403)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*allowed_roles: UserRole) -> Callable[[CurrentUser], User]:
    def dependency(current_user: CurrentUser) -> User:
        if current_user.role not in allowed_roles:
            raise AppError("FORBIDDEN", "当前账号无权执行此操作", 403)
        return current_user

    return dependency
