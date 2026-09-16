"""API routes for the resume optimization feature (Stage 3).

Endpoints
---------

* ``POST /api/resume-optimizations`` — generate a new optimization
* ``GET  /api/resume-optimizations`` — list owned optimizations
  (failed records are hidden by default)
* ``GET  /api/resume-optimizations/{id}`` — fetch one record
* ``POST /api/resume-optimizations/{id}/confirm`` — accept/reject/edit
  section suggestions
* ``POST /api/resume-optimizations/{id}/retry`` — regenerate a failed
  optimization as a new record
* ``POST /api/resume-optimizations/{id}/create-version`` — apply the
  confirmed suggestions to a new immutable ``ResumeVersion``

All routes require an authenticated user. The service layer enforces
ownership checks so user A cannot read or mutate user B's optimizations.
"""

from fastapi import APIRouter, Query, status

from app.api.dependencies import AppSettings, CurrentUser, DbSession
from app.integrations.dify.resume_optimization_providers import (
    FakeResumeOptimizationProvider,
    create_resume_optimization_provider,
)
from app.schemas.common import ApiResponse
from app.schemas.resume_optimizations import (
    ResumeOptimizationConfirmPayload,
    ResumeOptimizationCreate,
    ResumeOptimizationCreateVersionResult,
    ResumeOptimizationListRead,
    ResumeOptimizationRead,
)
from app.services.resume_optimizations import ResumeOptimizationService

router = APIRouter(prefix="/resume-optimizations", tags=["resume-optimizations"])


@router.post(
    "",
    response_model=ApiResponse[ResumeOptimizationRead],
    status_code=status.HTTP_201_CREATED,
    summary="Generate resume optimization suggestions for a job",
)
def create_resume_optimization(
    payload: ResumeOptimizationCreate,
    current_user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
) -> ApiResponse[ResumeOptimizationRead]:
    provider = create_resume_optimization_provider(settings)
    return ApiResponse(
        data=ResumeOptimizationService(session, provider).create(current_user.id, payload),
        message="Resume optimization generated",
    )


@router.get(
    "",
    response_model=ApiResponse[ResumeOptimizationListRead],
    summary="List the current user's resume optimizations",
)
def list_resume_optimizations(
    current_user: CurrentUser,
    session: DbSession,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    include_failed: bool = Query(default=False),
) -> ApiResponse[ResumeOptimizationListRead]:
    return ApiResponse(
        data=ResumeOptimizationService(
            session, FakeResumeOptimizationProvider()
        ).list_optimizations(
            current_user.id,
            offset=offset,
            limit=limit,
            include_failed=include_failed,
        )
    )


@router.get(
    "/{optimization_id}",
    response_model=ApiResponse[ResumeOptimizationRead],
    summary="Get one owned resume optimization",
)
def get_resume_optimization(
    optimization_id: int,
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[ResumeOptimizationRead]:
    return ApiResponse(
        data=ResumeOptimizationService(session, FakeResumeOptimizationProvider()).get(
            current_user.id, optimization_id
        )
    )


@router.post(
    "/{optimization_id}/confirm",
    response_model=ApiResponse[ResumeOptimizationRead],
    summary="Confirm section suggestions for a resume optimization",
)
def confirm_resume_optimization(
    optimization_id: int,
    payload: ResumeOptimizationConfirmPayload,
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[ResumeOptimizationRead]:
    return ApiResponse(
        data=ResumeOptimizationService(session, FakeResumeOptimizationProvider()).confirm(
            current_user.id, optimization_id, payload
        ),
        message="Resume optimization confirmed",
    )


@router.post(
    "/{optimization_id}/retry",
    response_model=ApiResponse[ResumeOptimizationRead],
    status_code=status.HTTP_201_CREATED,
    summary="Retry a failed resume optimization as a new record",
)
def retry_resume_optimization(
    optimization_id: int,
    current_user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
) -> ApiResponse[ResumeOptimizationRead]:
    provider = create_resume_optimization_provider(settings)
    return ApiResponse(
        data=ResumeOptimizationService(session, provider).retry(current_user.id, optimization_id),
        message="Resume optimization regenerated",
    )


@router.post(
    "/{optimization_id}/create-version",
    response_model=ApiResponse[ResumeOptimizationCreateVersionResult],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new resume version from a confirmed optimization",
)
def create_version_from_optimization(
    optimization_id: int,
    current_user: CurrentUser,
    session: DbSession,
) -> ApiResponse[ResumeOptimizationCreateVersionResult]:
    return ApiResponse(
        data=ResumeOptimizationService(session, FakeResumeOptimizationProvider()).create_version(
            current_user.id, optimization_id
        ),
        message="New resume version created",
    )
