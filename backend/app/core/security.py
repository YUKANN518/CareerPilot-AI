from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, Literal
from uuid import uuid4

import jwt
from jwt import InvalidTokenError
from pwdlib import PasswordHash

from app.core.config import Settings
from app.core.exceptions import AppError

password_hash = PasswordHash.recommended()
TokenType = Literal["access", "refresh"]


@dataclass(frozen=True)
class EncodedToken:
    value: str
    jti: str
    expires_at: datetime


def hash_password(plain_password: str) -> str:
    return password_hash.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)


def hash_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def create_token(
    subject: int,
    token_type: TokenType,
    settings: Settings,
    *,
    expires_delta: timedelta,
) -> EncodedToken:
    now = datetime.now(UTC)
    expires_at = now + expires_delta
    jti = str(uuid4())
    payload = {
        "sub": str(subject),
        "type": token_type,
        "jti": jti,
        "iat": now,
        "exp": expires_at,
    }
    value = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return EncodedToken(value=value, jti=jti, expires_at=expires_at)


def create_access_token(subject: int, settings: Settings) -> EncodedToken:
    return create_token(
        subject,
        "access",
        settings,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(subject: int, settings: Settings) -> EncodedToken:
    return create_token(
        subject,
        "refresh",
        settings,
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str, expected_type: TokenType, settings: Settings) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "type", "jti", "iat", "exp"]},
        )
    except InvalidTokenError as exc:
        raise AppError("INVALID_TOKEN", "令牌无效或已过期", 401) from exc

    if payload.get("type") != expected_type:
        raise AppError("INVALID_TOKEN_TYPE", "令牌类型不正确", 401)
    return payload


def create_match_sse_ticket(
    subject: int,
    run_id: int,
    settings: Settings,
) -> EncodedToken:
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=2)
    jti = str(uuid4())
    payload = {
        "sub": str(subject),
        "type": "match_sse",
        "run_id": run_id,
        "jti": jti,
        "iat": now,
        "exp": expires_at,
    }
    value = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return EncodedToken(value=value, jti=jti, expires_at=expires_at)


def decode_match_sse_ticket(token: str, run_id: int, settings: Settings) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "type", "run_id", "jti", "iat", "exp"]},
        )
    except InvalidTokenError as exc:
        raise AppError("INVALID_SSE_TICKET", "The event stream ticket is invalid", 401) from exc
    if payload.get("type") != "match_sse" or payload.get("run_id") != run_id:
        raise AppError("INVALID_SSE_TICKET", "The event stream ticket has the wrong scope", 401)
    return payload


def create_career_qa_sse_ticket(
    subject: int,
    run_id: int,
    settings: Settings,
) -> EncodedToken:
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=2)
    jti = str(uuid4())
    payload = {
        "sub": str(subject),
        "type": "career_qa_sse",
        "run_id": run_id,
        "jti": jti,
        "iat": now,
        "exp": expires_at,
    }
    value = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return EncodedToken(value=value, jti=jti, expires_at=expires_at)


def decode_career_qa_sse_ticket(token: str, run_id: int, settings: Settings) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "type", "run_id", "jti", "iat", "exp"]},
        )
    except InvalidTokenError as exc:
        raise AppError("INVALID_SSE_TICKET", "The event stream ticket is invalid", 401) from exc
    if payload.get("type") != "career_qa_sse" or payload.get("run_id") != run_id:
        raise AppError("INVALID_SSE_TICKET", "The event stream ticket has the wrong scope", 401)
    return payload
