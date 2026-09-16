import os
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

os.environ["AUTO_CREATE_TABLES"] = "false"
os.environ["JWT_SECRET_KEY"] = "test-only-secret-key-with-at-least-32-characters"

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.rate_limit import login_rate_limiter
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import build_engine, get_db_session
from app.main import app
from app.models.enums import UserRole
from app.models.users import User, UserProfile


@pytest.fixture(autouse=True)
def reset_login_rate_limiter() -> Generator[None, None, None]:
    login_rate_limiter.reset()
    yield
    login_rate_limiter.reset()


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="test",
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        jwt_secret_key="test-only-secret-key-with-at-least-32-characters",
        upload_directory=str(tmp_path / "uploads"),
        faiss_index_dir=str(tmp_path / "faiss"),
        ai_provider="mock",
        embedding_provider="fake",
        # Force fake provider in tests, regardless of any ../.env file that may
        # configure DIFY_PROVIDER_MODE=dify for real-connection smoke tests.
        dify_provider_mode="fake",
    )


@pytest.fixture
def db_session(tmp_path: Path) -> Generator[Session, None, None]:
    database_path = tmp_path / "test.db"
    engine = build_engine(f"sqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with testing_session() as session:
        yield session
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
async def client(
    db_session: Session,
    test_settings: Settings,
) -> AsyncGenerator[AsyncClient, None]:
    def override_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_settings] = lambda: test_settings
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def admin_user(db_session: Session) -> User:
    user = User(
        email="admin@example.com",
        password_hash=hash_password("AdminPassword123!"),
        role=UserRole.ADMIN,
        profile=UserProfile(display_name="Admin"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user
