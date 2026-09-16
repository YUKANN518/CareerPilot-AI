from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.bootstrap import ensure_local_demo_admin


async def register_user(client: AsyncClient, email: str = "user@example.com") -> dict[str, object]:
    response = await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "StrongPassword123!",
            "display_name": "Test User",
        },
    )
    assert response.status_code == 201
    return response.json()["data"]


async def test_register_and_get_current_user(client: AsyncClient) -> None:
    auth_session = await register_user(client)
    access_token = auth_session["tokens"]["access_token"]

    response = await client.get(
        "/api/users/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["email"] == "user@example.com"
    assert response.json()["data"]["role"] == "USER"
    assert response.json()["data"]["profile"]["display_name"] == "Test User"


async def test_duplicate_registration_returns_stable_error(client: AsyncClient) -> None:
    await register_user(client)
    response = await client.post(
        "/api/auth/register",
        json={
            "email": "USER@example.com",
            "password": "StrongPassword123!",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"


async def test_login_rejects_wrong_password_and_accepts_valid_password(
    client: AsyncClient,
) -> None:
    await register_user(client)

    rejected = await client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "wrong"},
    )
    accepted = await client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "StrongPassword123!"},
    )

    assert rejected.status_code == 401
    assert rejected.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert accepted.status_code == 200
    assert accepted.json()["data"]["tokens"]["token_type"] == "bearer"


async def test_login_rate_limit_blocks_repeated_failures(
    client: AsyncClient,
    test_settings: Settings,
) -> None:
    test_settings.login_rate_limit_attempts = 2
    test_settings.login_rate_limit_window_seconds = 60
    test_settings.login_rate_limit_lock_seconds = 60
    payload = {"email": "limited@example.com", "password": "WrongPassword123!"}

    first = await client.post("/api/auth/login", json=payload)
    second = await client.post("/api/auth/login", json=payload)
    blocked = await client.post("/api/auth/login", json=payload)

    assert first.status_code == 401
    assert second.status_code == 401
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "LOGIN_RATE_LIMITED"


async def test_local_demo_admin_can_log_in(
    client: AsyncClient,
    db_session: Session,
) -> None:
    ensure_local_demo_admin(
        db_session,
        Settings(
            app_env="development",
            database_url="sqlite:///:memory:",
            jwt_secret_key="test-only-secret-key-with-at-least-32-characters",
        ),
    )

    response = await client.post(
        "/api/auth/login",
        json={"email": "admin@careerpilot.local", "password": "Admin123456!"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["user"]["role"] == "ADMIN"


async def test_refresh_token_is_rotated(client: AsyncClient) -> None:
    auth_session = await register_user(client)
    old_refresh_token = auth_session["tokens"]["refresh_token"]

    refreshed = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": old_refresh_token},
    )
    replay = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": old_refresh_token},
    )

    assert refreshed.status_code == 200
    assert refreshed.json()["data"]["refresh_token"] != old_refresh_token
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "REFRESH_TOKEN_REVOKED"


async def test_protected_route_requires_access_token(client: AsyncClient) -> None:
    response = await client.get("/api/users/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


async def test_update_current_user_profile(client: AsyncClient) -> None:
    auth_session = await register_user(client)
    access_token = auth_session["tokens"]["access_token"]

    response = await client.patch(
        "/api/users/me",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "display_name": "Updated",
            "location": "Shanghai",
            "target_roles": ["Backend Engineer"],
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["profile"]["display_name"] == "Updated"
    assert response.json()["data"]["profile"]["location"] == "Shanghai"


async def test_rbac_rejects_user_and_allows_admin(client: AsyncClient, admin_user: object) -> None:
    user_session = await register_user(client)
    user_access_token = user_session["tokens"]["access_token"]
    user_response = await client.get(
        "/api/admin/knowledge-documents",
        headers={"Authorization": f"Bearer {user_access_token}"},
    )

    admin_login = await client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "AdminPassword123!"},
    )
    admin_access_token = admin_login.json()["data"]["tokens"]["access_token"]
    admin_response = await client.get(
        "/api/admin/knowledge-documents",
        headers={"Authorization": f"Bearer {admin_access_token}"},
    )

    assert user_response.status_code == 403
    assert user_response.json()["error"]["code"] == "FORBIDDEN"
    assert admin_response.status_code == 200
    assert admin_response.json()["data"]["total"] == 0
