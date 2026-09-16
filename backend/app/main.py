from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401
from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.services.bootstrap import ensure_local_demo_admin
from app.services.knowledge_index_jobs import knowledge_index_job_runner

settings = get_settings()


def ensure_sqlite_directory(database_url: str) -> None:
    prefix = "sqlite:///"
    if database_url.startswith(prefix) and database_url != "sqlite:///:memory:":
        database_path = Path(database_url.removeprefix(prefix))
        database_path.parent.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    if settings.auto_create_tables:
        ensure_sqlite_directory(settings.database_url)
        Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        ensure_local_demo_admin(session, settings)
    knowledge_index_job_runner.recover_interrupted(settings=settings, session_factory=SessionLocal)
    try:
        yield
    finally:
        knowledge_index_job_runner.shutdown()


app = FastAPI(
    title=settings.app_name,
    version="0.4.0",
    description="CareerPilot AI API - 基于证据约束的人岗匹配与求职决策后端",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_exception_handlers(app)
app.include_router(api_router, prefix=settings.api_v1_prefix)
