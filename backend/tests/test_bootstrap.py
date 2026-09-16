from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import verify_password
from app.models.enums import UserRole
from app.models.users import User
from app.repositories.users import UserRepository
from app.services.bootstrap import ensure_local_demo_admin


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "development",
        "database_url": "sqlite:///:memory:",
        "jwt_secret_key": "test-only-secret-key-with-at-least-32-characters",
    }
    values.update(overrides)
    return Settings(**values)


def test_creates_local_demo_admin_with_hashed_password(db_session: Session) -> None:
    settings = _settings()

    assert ensure_local_demo_admin(db_session, settings) is True

    user = UserRepository(db_session).get_by_email("admin@careerpilot.local")
    assert user is not None
    assert user.role == UserRole.ADMIN
    assert user.is_active is True
    assert user.password_hash != "Admin123456!"
    assert verify_password("Admin123456!", user.password_hash) is True
    assert user.profile is not None
    assert user.profile.display_name == "CareerPilot Demo Admin"


def test_demo_admin_bootstrap_is_idempotent_and_does_not_reset_password(
    db_session: Session,
) -> None:
    settings = _settings()
    assert ensure_local_demo_admin(db_session, settings) is True
    user = UserRepository(db_session).get_by_email("admin@careerpilot.local")
    assert user is not None
    original_hash = user.password_hash

    assert ensure_local_demo_admin(db_session, settings) is False

    db_session.refresh(user)
    assert user.password_hash == original_hash
    assert db_session.query(User).count() == 1


def test_demo_admin_is_not_created_outside_local_environments(db_session: Session) -> None:
    settings = _settings(app_env="production")

    assert ensure_local_demo_admin(db_session, settings) is False
    assert UserRepository(db_session).get_by_email("admin@careerpilot.local") is None


def test_demo_admin_can_be_disabled(db_session: Session) -> None:
    settings = _settings(demo_admin_enabled=False)

    assert ensure_local_demo_admin(db_session, settings) is False
    assert UserRepository(db_session).get_by_email("admin@careerpilot.local") is None
