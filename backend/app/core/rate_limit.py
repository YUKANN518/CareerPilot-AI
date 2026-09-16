from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from hashlib import sha256
from threading import Lock
from time import monotonic

from fastapi import Request

from app.core.config import Settings
from app.core.exceptions import AppError


@dataclass
class _LoginBucket:
    failures: deque[float] = field(default_factory=deque)
    blocked_until: float = 0.0


class LoginRateLimiter:
    """Process-local failed-login limiter without retaining raw email addresses."""

    def __init__(self) -> None:
        self._buckets: dict[str, _LoginBucket] = {}
        self._lock = Lock()

    def check(self, key: str, settings: Settings) -> None:
        now = monotonic()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                return
            if bucket.blocked_until > now:
                raise AppError(
                    "LOGIN_RATE_LIMITED",
                    "登录尝试过于频繁，请稍后再试",
                    429,
                )
            self._purge(bucket, now, settings.login_rate_limit_window_seconds)
            if not bucket.failures:
                self._buckets.pop(key, None)

    def record_failure(self, key: str, settings: Settings) -> None:
        now = monotonic()
        with self._lock:
            bucket = self._buckets.setdefault(key, _LoginBucket())
            self._purge(bucket, now, settings.login_rate_limit_window_seconds)
            bucket.failures.append(now)
            if len(bucket.failures) >= settings.login_rate_limit_attempts:
                bucket.blocked_until = now + settings.login_rate_limit_lock_seconds

    def clear(self, key: str) -> None:
        with self._lock:
            self._buckets.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()

    @staticmethod
    def _purge(bucket: _LoginBucket, now: float, window_seconds: int) -> None:
        cutoff = now - window_seconds
        while bucket.failures and bucket.failures[0] <= cutoff:
            bucket.failures.popleft()


def login_rate_limit_key(request: Request, email: str) -> str:
    client_host = request.client.host if request.client is not None else "unknown"
    normalized_email = email.strip().casefold()
    return sha256(f"{client_host}|{normalized_email}".encode()).hexdigest()


login_rate_limiter = LoginRateLimiter()
