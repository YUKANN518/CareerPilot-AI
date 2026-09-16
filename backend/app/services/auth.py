from __future__ import annotations

from datetime import UTC, datetime
from hmac import compare_digest

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import AppError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.enums import UserRole
from app.models.users import RefreshToken, User, UserProfile
from app.repositories.tokens import RefreshTokenRepository
from app.repositories.users import UserRepository
from app.schemas.auth import AuthSession, TokenPair
from app.schemas.user import UserRead

_DUMMY_PASSWORD_HASH = hash_password("careerpilot-invalid-user-password")


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class AuthService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.users = UserRepository(session)
        self.tokens = RefreshTokenRepository(session)

    def register(self, email: str, password: str, display_name: str | None) -> AuthSession:
        normalized_email = email.strip().casefold()
        if self.users.get_by_email(normalized_email) is not None:
            raise AppError("EMAIL_ALREADY_REGISTERED", "该邮箱已注册", 409)

        user = User(
            email=normalized_email,
            password_hash=hash_password(password),
            role=UserRole.USER,
            profile=UserProfile(display_name=display_name),
        )
        try:
            self.users.add(user)
            token_pair = self._issue_token_pair(user)
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise AppError("EMAIL_ALREADY_REGISTERED", "该邮箱已注册", 409) from exc
        return AuthSession(user=UserRead.model_validate(user), tokens=token_pair)

    def login(self, email: str, password: str) -> AuthSession:
        normalized_email = email.strip().casefold()
        user = self.users.get_by_email(normalized_email)
        password_is_valid = verify_password(
            password,
            user.password_hash if user is not None else _DUMMY_PASSWORD_HASH,
        )
        if user is None or not password_is_valid:
            raise AppError("INVALID_CREDENTIALS", "邮箱或密码不正确", 401)
        if not user.is_active:
            raise AppError("USER_DISABLED", "账号已停用", 403)

        user.last_login_at = datetime.now(UTC)
        token_pair = self._issue_token_pair(user)
        self.session.commit()
        return AuthSession(user=UserRead.model_validate(user), tokens=token_pair)

    def refresh(self, raw_refresh_token: str) -> TokenPair:
        payload = decode_token(raw_refresh_token, "refresh", self.settings)
        try:
            user_id = int(payload["sub"])
            jti = str(payload["jti"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AppError("INVALID_TOKEN", "令牌内容无效", 401) from exc

        stored_token = self.tokens.get_by_jti(jti)
        now = datetime.now(UTC)
        if (
            stored_token is None
            or stored_token.user_id != user_id
            or stored_token.revoked_at is not None
            or _as_utc(stored_token.expires_at) <= now
            or not compare_digest(stored_token.token_hash, hash_token(raw_refresh_token))
        ):
            raise AppError("REFRESH_TOKEN_REVOKED", "刷新令牌已失效", 401)

        user = self.users.get_by_id(user_id)
        if user is None or not user.is_active:
            raise AppError("USER_DISABLED", "账号不存在或已停用", 403)

        access = create_access_token(user.id, self.settings)
        replacement = create_refresh_token(user.id, self.settings)
        stored_token.revoked_at = now
        stored_token.replaced_by_jti = replacement.jti
        self.tokens.add(
            RefreshToken(
                user_id=user.id,
                jti=replacement.jti,
                token_hash=hash_token(replacement.value),
                expires_at=replacement.expires_at,
            )
        )
        self.session.commit()
        return TokenPair(
            access_token=access.value,
            refresh_token=replacement.value,
            expires_in=self.settings.access_token_expire_minutes * 60,
        )

    def logout(self, raw_refresh_token: str) -> None:
        payload = decode_token(raw_refresh_token, "refresh", self.settings)
        stored_token = self.tokens.get_by_jti(str(payload["jti"]))
        if stored_token is not None and stored_token.revoked_at is None:
            stored_token.revoked_at = datetime.now(UTC)
            self.session.commit()

    def _issue_token_pair(self, user: User) -> TokenPair:
        access = create_access_token(user.id, self.settings)
        refresh = create_refresh_token(user.id, self.settings)
        self.tokens.add(
            RefreshToken(
                user_id=user.id,
                jti=refresh.jti,
                token_hash=hash_token(refresh.value),
                expires_at=refresh.expires_at,
            )
        )
        return TokenPair(
            access_token=access.value,
            refresh_token=refresh.value,
            expires_in=self.settings.access_token_expire_minutes * 60,
        )
